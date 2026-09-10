/**
 * Gantt encoding, split across two axes so the view matches the Excel tracker:
 *
 * - Risk level (`GanttRiskLevel`) colors the timeline bars.
 * - Task status (`GanttVisualStatus`) drives the left-hand 状态 column and the
 *   legend filter. Priority (highest first): cancelled / completed / delayed
 *   (ai_status or past due) / at risk / in progress / not started.
 *
 * CSS classes use the SVAR bar type hook:
 * custom types → `wx-bar wx-task <type>` (e.g. `gantt_high_risk`).
 */

import type { Task, TaskAiStatus, TaskStatus } from "@/types/task";

export type GanttVisualStatus =
  | "not_started"
  | "progress"
  | "completed"
  | "risk"
  | "delayed"
  | "paused";

/**
 * Risk level drives the bar color, mirroring the Excel tracker's `Category`
 * column (On track / Low risk / Med risk / High risk / Unassigned).
 * Task status still drives the left-hand 状态 column.
 */
export type GanttRiskLevel = "on_track" | "low_risk" | "med_risk" | "high_risk" | "unassigned";

/** SVAR `task.type` values — render as `wx-bar wx-task <id>` (except built-ins). */
export type GanttBarType =
  | "gantt_on_track"
  | "gantt_low_risk"
  | "gantt_med_risk"
  | "gantt_high_risk"
  | "gantt_unassigned"
  | "summary"
  | "milestone";

export type GanttStatusMeta = {
  id: GanttVisualStatus;
  label: string;
  /** Status dot / badge accent */
  color: string;
  /** Badge background */
  track: string;
};

/**
 * Canonical palette — mirrored as `--gantt-status-*` CSS tokens.
 * Keep in sync with `globals.css`.
 */
export const GANTT_STATUS_META: Record<GanttVisualStatus, GanttStatusMeta> = {
  not_started: { id: "not_started", label: "未开始", color: "#94A3B8", track: "#E2E8F0" },
  progress: { id: "progress", label: "进行中", color: "#3B82F6", track: "#BFDBFE" },
  completed: { id: "completed", label: "已完成", color: "#22C55E", track: "#DCFCE7" },
  risk: { id: "risk", label: "存在风险", color: "#F59E0B", track: "#FEF3C7" },
  delayed: { id: "delayed", label: "已延期", color: "#EF4444", track: "#FEE2E2" },
  paused: { id: "paused", label: "已暂停", color: "#8B5CF6", track: "#DDD6FE" },
};

export const GANTT_STATUS_ORDER: GanttVisualStatus[] = [
  "progress",
  "completed",
  "risk",
  "delayed",
  "not_started",
  "paused",
];

export type GanttRiskMeta = {
  id: GanttRiskLevel;
  label: string;
  /** SVAR task.type / CSS suffix */
  barType: GanttBarType;
  /** Solid bar fill and legend swatch */
  color: string;
  /** Readable text color on top of `color` */
  onColor: string;
};

/**
 * Risk palette lifted from the Excel tracker's theme so the two artefacts read
 * identically. Mirrored as `--gantt-risk-*` CSS tokens in globals.css.
 */
export const GANTT_RISK_META: Record<GanttRiskLevel, GanttRiskMeta> = {
  on_track: {
    id: "on_track",
    label: "正常",
    barType: "gantt_on_track",
    color: "#20A472",
    onColor: "#FFFFFF",
  },
  low_risk: {
    id: "low_risk",
    label: "低风险",
    barType: "gantt_low_risk",
    color: "#00B0F0",
    onColor: "#FFFFFF",
  },
  med_risk: {
    id: "med_risk",
    label: "中风险",
    barType: "gantt_med_risk",
    color: "#4868E5",
    onColor: "#FFFFFF",
  },
  high_risk: {
    id: "high_risk",
    label: "高风险",
    barType: "gantt_high_risk",
    color: "#842D96",
    onColor: "#FFFFFF",
  },
  unassigned: {
    id: "unassigned",
    label: "未分配",
    barType: "gantt_unassigned",
    color: "#E5E5E5",
    onColor: "#475569",
  },
};

export const GANTT_RISK_ORDER: GanttRiskLevel[] = [
  "on_track",
  "low_risk",
  "med_risk",
  "high_risk",
  "unassigned",
];

export const GANTT_TASK_TYPES = [
  { id: "task", label: "任务" },
  { id: "summary", label: "汇总" },
  { id: "milestone", label: "里程碑" },
  ...GANTT_RISK_ORDER.map((id) => ({
    id: GANTT_RISK_META[id].barType,
    label: GANTT_RISK_META[id].label,
  })),
];

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function isPastDue(task: Task, today: Date): boolean {
  if (!task.due_date) return false;
  if (task.status === "COMPLETED" || task.status === "CANCELLED") return false;
  return parseLocalDate(task.due_date) < startOfLocalDay(today);
}

/**
 * Resolve the single visual status a bar should show.
 * Abnormal states always beat phase / progress / normal status.
 */
export function resolveGanttStatus(task: Task, today: Date = new Date()): GanttVisualStatus {
  if (task.status === "CANCELLED") return "paused";
  if (task.status === "COMPLETED") return "completed";

  const riskSignal: TaskAiStatus | null = task.ai_status ?? task.ai_risk_level;
  if (riskSignal === "DELAYED" || isPastDue(task, today)) return "delayed";
  if (riskSignal === "AT_RISK") return "risk";

  if (task.status === "IN_PROGRESS") return "progress";
  return "not_started";
}

/**
 * Resolve the risk level that colors the bar.
 *
 * The LLM analyzer fills `ai_status`; until it runs, an on-schedule task is
 * treated as low risk rather than silently claiming it is on track.
 */
export function resolveGanttRisk(task: Task, today: Date = new Date()): GanttRiskLevel {
  if (task.status === "CANCELLED") return "unassigned";

  const riskSignal: TaskAiStatus | null = task.ai_status ?? task.ai_risk_level;
  if (riskSignal === "DELAYED" || isPastDue(task, today)) return "high_risk";
  if (riskSignal === "AT_RISK") return "med_risk";
  if (riskSignal === "ON_TRACK" || task.status === "COMPLETED") return "on_track";
  return "low_risk";
}

export function ganttBarTypeFor(task: Task, today: Date = new Date()): GanttBarType {
  return GANTT_RISK_META[resolveGanttRisk(task, today)].barType;
}

export function ganttStatusLabel(status: TaskStatus | GanttVisualStatus | string): string {
  if (status in GANTT_STATUS_META) {
    return GANTT_STATUS_META[status as GanttVisualStatus].label;
  }
  const byTaskStatus: Record<TaskStatus, string> = {
    TODO: GANTT_STATUS_META.not_started.label,
    IN_PROGRESS: GANTT_STATUS_META.progress.label,
    COMPLETED: GANTT_STATUS_META.completed.label,
    CANCELLED: GANTT_STATUS_META.paused.label,
  };
  return byTaskStatus[status as TaskStatus] ?? String(status);
}
