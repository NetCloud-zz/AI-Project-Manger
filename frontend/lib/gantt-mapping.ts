import type { ILink, ITask } from "@svar-ui/react-gantt";

import { ganttBarTypeFor, resolveGanttRisk, resolveGanttStatus } from "@/lib/gantt-status";
import type { TaskLink, TaskLinkType } from "@/types/gantt";
import type { Task } from "@/types/task";

type TLinkType = ILink["type"];

const LINK_TYPE_TO_SVAR: Record<TaskLinkType, TLinkType> = {
  FINISH_TO_START: "e2s",
  START_TO_START: "s2s",
  FINISH_TO_FINISH: "e2e",
  START_TO_FINISH: "s2e",
};

const SVAR_TO_LINK_TYPE: Record<TLinkType, TaskLinkType> = {
  e2s: "FINISH_TO_START",
  s2s: "START_TO_START",
  e2e: "FINISH_TO_FINISH",
  s2e: "START_TO_FINISH",
};

export function toSvarLinkType(value: TaskLinkType): TLinkType {
  return LINK_TYPE_TO_SVAR[value] ?? "e2s";
}

export function fromSvarLinkType(value: TLinkType | string | undefined): TaskLinkType {
  if (!value) return "FINISH_TO_START";
  return SVAR_TO_LINK_TYPE[value as TLinkType] ?? "FINISH_TO_START";
}

/** Parse a `YYYY-MM-DD` API date as local midnight, avoiding UTC shifts. */
export function parseApiDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Format a Date back to `YYYY-MM-DD` in local time. */
export function formatApiDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** Label for tasks with no work stream — always sorted last. */
export const UNGROUPED_LABEL = "未分组";

/** Group rows get synthetic negative ids so they never collide with task ids. */
function groupRowId(index: number): number {
  return -(index + 1);
}

/**
 * SVAR treats `end` as exclusive, so a task due on the 10th must end on the
 * 11th to render a bar that covers the whole due day.
 *
 * Undated tasks (no start/due) get a one-day placeholder bar on `today`.
 *
 * `type` encodes risk level so CSS can color bars without hardcoding in JS.
 */
export function toSvarTask(task: Task, today: Date = new Date(), parent = 0): ITask {
  const { start, end } = taskBarSpan(task, today);

  return {
    id: task.id,
    text: task.task_name,
    start,
    end,
    progress: task.progress_percent ?? 0,
    type: ganttBarTypeFor(task, today),
    parent,
    owner: task.owner?.name ?? "",
    owner_id: task.owner_id,
    status: task.status,
    ai_status: task.ai_status,
    visual_status: resolveGanttStatus(task, today),
    risk_level: resolveGanttRisk(task, today),
    work_stream: task.work_stream ?? "",
    days: Math.round((end.getTime() - start.getTime()) / MS_PER_DAY),
  };
}

function taskBarSpan(task: Task, today: Date): { start: Date; end: Date } {
  if (task.start_date || task.due_date) {
    const start = parseApiDate(task.start_date ?? task.due_date!);
    const end = parseApiDate(task.due_date ?? task.start_date!);
    end.setDate(end.getDate() + 1);
    return { start, end };
  }
  const start = startOfLocalDay(today);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { start, end };
}

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

/**
 * Flatten tasks into the section-header + indented-children shape used by the
 * Excel tracker. Sections are ordered by their earliest start date so the
 * timeline reads top-left to bottom-right; the ungrouped bucket comes last.
 */
export function toSvarRows(tasks: Task[], today: Date = new Date()): ITask[] {
  const buckets = new Map<string, Task[]>();
  for (const task of tasks) {
    const key = task.work_stream?.trim() || UNGROUPED_LABEL;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(task);
    else buckets.set(key, [task]);
  }

  const startOf = (task: Task) => {
    const raw = task.start_date ?? task.due_date;
    return raw ? parseApiDate(raw).getTime() : Number.MAX_SAFE_INTEGER;
  };
  const sections = [...buckets.entries()].sort((a, b) => {
    if (a[0] === UNGROUPED_LABEL) return 1;
    if (b[0] === UNGROUPED_LABEL) return -1;
    const aMin = Math.min(...a[1].map(startOf));
    const bMin = Math.min(...b[1].map(startOf));
    return aMin - bMin;
  });

  // A single unnamed bucket means nobody uses work streams yet — stay flat.
  if (sections.length === 1 && sections[0][0] === UNGROUPED_LABEL) {
    return sections[0][1].map((task) => toSvarTask(task, today));
  }

  const rows: ITask[] = [];
  sections.forEach(([label, members], index) => {
    const id = groupRowId(index);
    const sorted = [...members].sort((a, b) => startOf(a) - startOf(b));
    const dated = sorted.filter((task) => task.start_date || task.due_date);
    const spanSource = dated.length ? dated : sorted;
    const starts = spanSource.map((task) => taskBarSpan(task, today).start.getTime());
    const ends = spanSource.map((task) => taskBarSpan(task, today).end.getTime());

    rows.push({
      id,
      text: label,
      start: new Date(Math.min(...starts)),
      end: new Date(Math.max(...ends)),
      type: "summary",
      parent: 0,
      open: true,
      is_group: true,
      task_count: sorted.length,
    });
    for (const task of sorted) {
      rows.push(toSvarTask(task, today, id));
    }
  });
  return rows;
}

export function toSvarLink(link: TaskLink): ILink {
  return {
    id: link.id,
    source: link.source_id,
    target: link.target_id,
    type: toSvarLinkType(link.link_type),
  };
}

/** Convert an edited SVAR bar back into the API's inclusive due date. */
export function svarDatesToApi(start: Date | undefined, end: Date | undefined): {
  start_date?: string;
  due_date?: string;
} {
  const patch: { start_date?: string; due_date?: string } = {};
  if (start) {
    patch.start_date = formatApiDate(start);
  }
  if (end) {
    const inclusive = new Date(end);
    inclusive.setDate(inclusive.getDate() - 1);
    if (start && inclusive < start) {
      patch.due_date = formatApiDate(start);
    } else {
      patch.due_date = formatApiDate(inclusive);
    }
  }
  return patch;
}

export function clampProgress(value: number | undefined): number | undefined {
  if (value === undefined || Number.isNaN(value)) return undefined;
  return Math.max(0, Math.min(100, Math.round(value)));
}
