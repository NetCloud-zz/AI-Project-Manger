"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { App, Button, InputNumber, Segmented, Select, Space, Tooltip } from "antd";
import {
  CloseOutlined,
  LeftOutlined,
  MinusOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { Gantt, Willow } from "@svar-ui/react-gantt";
import type { IApi, IScaleConfig } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";

import { EmptyState } from "@/components/feedback/EmptyState";
import { LoadingState } from "@/components/feedback/LoadingState";
import {
  clampProgress,
  fromSvarLinkType,
  toSvarLink,
  toSvarRows,
} from "@/lib/gantt-mapping";
import {
  GANTT_RISK_META,
  GANTT_RISK_ORDER,
  GANTT_STATUS_META,
  GANTT_TASK_TYPES,
  type GanttRiskLevel,
  type GanttVisualStatus,
  resolveGanttRisk,
} from "@/lib/gantt-status";
import {
  createTaskLink,
  deleteTaskLink,
  fetchProjectGantt,
  updateTaskLink,
} from "@/services/gantt";
import { updateTask } from "@/services/tasks";
import { fetchAssignableUsers, fetchProjectForecast } from "@/services/projects";
import type { ProjectForecast } from "@/types/forecast";
import type { ProjectOwnerBrief } from "@/types/project";
import { ScheduleImpactModal } from "@/components/project/ScheduleImpactModal";
import { scheduleImpactOf, type ScheduleImpact } from "@/lib/schedule-impact";
import { useViewport } from "@/hooks/useViewport";
import type { ProjectGanttData } from "@/types/gantt";

type ZoomLevel = "day" | "week" | "month";
type MobilePane = "timeline" | "list";

const GRID_WIDTH_DESKTOP = 664;
const GRID_WIDTH_MOBILE_TIMELINE = 148;
const GRID_WIDTH_MOBILE_LIST = 280;

/**
 * One line of prediction next to the chart title. It says the predicted finish
 * and how it compares with the commitment, and it never restates the target as
 * if it had moved.
 */
function ForecastNote({ forecast }: { forecast: ProjectForecast }) {
  if (!forecast.computable) {
    return (
      <Tooltip title={forecast.conflicts[0]?.message ?? "排期引擎没有返回结果"}>
        <span className="gantt-forecast-note gantt-forecast-note--unknown">
          当前数据算不出预测完成日期
        </span>
      </Tooltip>
    );
  }
  const variance = forecast.variance_calendar_days;
  const late = forecast.verdict === "BEHIND";
  return (
    <Tooltip title="按当前计划、依赖和工作日历推算；红框任务在关键路径上，没有机动时间。">
      <span className={`gantt-forecast-note${late ? " gantt-forecast-note--late" : ""}`}>
        预测完成 {forecast.predicted_finish_date}
        {forecast.target_date && variance
          ? `（${variance > 0 ? "晚于" : "早于"}目标 ${Math.abs(variance)} 天）`
          : ""}
      </span>
    </Tooltip>
  );
}

/** Shape of a row as produced by `toSvarRows` — task rows plus section headers. */
type GanttRow = {
  id?: string | number;
  text?: string;
  start?: Date;
  progress?: number;
  owner?: string;
  owner_id?: number | null;
  days?: number;
  visual_status?: GanttVisualStatus;
  risk_level?: GanttRiskLevel;
  is_group?: boolean;
  task_count?: number;
};

type OwnerChoice = { value: number; label: string };

const MONTH_LABELS = [
  "1月",
  "2月",
  "3月",
  "4月",
  "5月",
  "6月",
  "7月",
  "8月",
  "9月",
  "10月",
  "11月",
  "12月",
];

/** Weekday initials, matching the Excel tracker's `S M T W T F S` header row. */
const WEEKDAY_INITIALS = ["日", "一", "二", "三", "四", "五", "六"];

const SCALES: Record<ZoomLevel, IScaleConfig[]> = {
  day: [
    { unit: "month", step: 1, format: (date: Date) => `${date.getFullYear()} ${MONTH_LABELS[date.getMonth()]}` },
    { unit: "day", step: 1, format: (date: Date) => String(date.getDate()) },
    { unit: "day", step: 1, format: (date: Date) => WEEKDAY_INITIALS[date.getDay()] },
  ],
  week: [
    { unit: "month", step: 1, format: (date: Date) => `${date.getFullYear()} ${MONTH_LABELS[date.getMonth()]}` },
    { unit: "week", step: 1, format: (date: Date) => `${date.getMonth() + 1}/${date.getDate()}` },
  ],
  month: [
    { unit: "year", step: 1, format: (date: Date) => `${date.getFullYear()} 年` },
    { unit: "month", step: 1, format: (date: Date) => MONTH_LABELS[date.getMonth()] },
  ],
};

const CELL_WIDTH: Record<ZoomLevel, number> = { day: 30, week: 56, month: 84 };
const ROW_HEIGHT = 30;
const SCALE_HEIGHT = 22;
const ZOOM_MIN = 50;
const ZOOM_MAX = 200;
const ZOOM_STEP = 10;

const HELP_TEXT =
  "双击「进度」可改百分比，双击「负责人」可换人；拖拽条上进度柄也可调进度。在任务两端拖出连线可创建依赖。任务时间请在任务详情中修改。只读模式下仅可浏览。";

function startOfToday(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** Stop SVAR from treating an edit gesture as a row / bar selection. */
function stopCellEvent(event: { stopPropagation(): void; preventDefault(): void }) {
  event.stopPropagation();
  event.preventDefault();
}

function ProgressEditCell({
  row,
  editable,
  onCommit,
}: {
  row: GanttRow;
  editable: boolean;
  onCommit: (taskId: number, progress: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(0);
  const [saving, setSaving] = useState(false);

  if (row.is_group) return "";
  const value = Math.max(0, Math.min(100, Math.round(row.progress ?? 0)));
  const taskId = Number(row.id);

  const begin = (event: ReactMouseEvent) => {
    if (!editable || saving) return;
    stopCellEvent(event);
    setDraft(value);
    setEditing(true);
  };

  const finish = async (next: number | null) => {
    if (!editing || saving) return;
    const progress = clampProgress(next ?? draft);
    setEditing(false);
    if (progress === undefined || progress === value) return;
    setSaving(true);
    try {
      await onCommit(taskId, progress);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <InputNumber
        className="gantt-progress-editor"
        size="small"
        min={0}
        max={100}
        precision={0}
        autoFocus
        controls={false}
        value={draft}
        disabled={saving}
        onClick={stopCellEvent}
        onMouseDown={stopCellEvent}
        onDoubleClick={stopCellEvent}
        onChange={(next) => setDraft(typeof next === "number" ? next : 0)}
        onPressEnter={() => void finish(draft)}
        onBlur={() => void finish(draft)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            stopCellEvent(event);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <span
      className={`gantt-progress-cell${editable ? " is-editable" : ""}`}
      title={editable ? "双击编辑进度" : undefined}
      onDoubleClick={begin}
      onMouseDown={(event) => {
        // Keep a pending double-click from selecting the whole row.
        if (editable) event.stopPropagation();
      }}
    >
      <span className="gantt-progress-cell__bar" style={{ width: `${value}%` }} />
      <span className="gantt-progress-cell__text">{value}%</span>
    </span>
  );
}

function OwnerEditCell({
  row,
  editable,
  options,
  onCommit,
}: {
  row: GanttRow;
  editable: boolean;
  options: OwnerChoice[];
  onCommit: (taskId: number, ownerId: number | null) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  if (row.is_group) return "";
  const taskId = Number(row.id);
  const ownerId = row.owner_id;

  const begin = (event: ReactMouseEvent) => {
    if (!editable || saving || options.length === 0) return;
    stopCellEvent(event);
    setEditing(true);
  };

  const pick = async (next: number | null) => {
    setEditing(false);
    if (next === ownerId) return;
    if (next == null && ownerId == null) return;
    setSaving(true);
    try {
      await onCommit(taskId, next);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <Select
        className="gantt-owner-editor"
        size="small"
        showSearch
        allowClear
        autoFocus
        defaultOpen
        disabled={saving}
        value={ownerId ?? undefined}
        options={options}
        optionFilterProp="label"
        placeholder="待定"
        getPopupContainer={() => document.body}
        onClick={stopCellEvent}
        onMouseDown={stopCellEvent}
        onChange={(next) => void pick(next == null ? null : Number(next))}
        onDropdownVisibleChange={(open) => {
          if (!open) setEditing(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            stopCellEvent(event);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <span
      className={`gantt-owner-cell${editable ? " is-editable" : ""}`}
      title={editable ? "双击更换负责人（可清空为待定）" : undefined}
      onDoubleClick={begin}
      onMouseDown={(event) => {
        if (editable) event.stopPropagation();
      }}
    >
      {row.owner || "待定"}
    </span>
  );
}

/**
 * Always-visible legend strip, mirroring the coloured chips at the top of the
 * Excel tracker. Chips double as a risk-level filter.
 */
function GanttLegend({
  active,
  onToggle,
  counts,
  showCritical,
}: {
  active: GanttRiskLevel | null;
  onToggle: (risk: GanttRiskLevel) => void;
  counts: Record<GanttRiskLevel, number>;
  showCritical: boolean;
}) {
  return (
    <div className="gantt-legend">
      <span className="gantt-legend__caption">图例</span>
      {GANTT_RISK_ORDER.map((id) => {
        const meta = GANTT_RISK_META[id];
        const count = counts[id] ?? 0;
        return (
          <button
            key={id}
            type="button"
            className={`gantt-legend__chip${active === id ? " is-active" : ""}`}
            style={{ background: meta.color, color: meta.onColor }}
            onClick={() => onToggle(id)}
            title={count ? `筛选「${meta.label}」（${count}）` : meta.label}
          >
            {meta.label}
            {count ? ` · ${count}` : ""}
          </button>
        );
      })}
      <span className="gantt-legend__note">
        <span className="gantt-legend__today-line" />
        今天
      </span>
      {showCritical ? (
        <span className="gantt-legend__note">
          <span className="gantt-legend__critical-box" />
          关键路径（无机动时间）
        </span>
      ) : null}
      <span className="gantt-legend__hint">点击色块可筛选；再点一次清除</span>
    </div>
  );
}

export function ProjectGantt({
  projectId,
  onClose,
}: {
  projectId: number;
  onClose?: () => void;
}) {
  const { message } = App.useApp();
  const viewport = useViewport();
  const isMobile = viewport === "mobile";
  const [data, setData] = useState<ProjectGanttData | null>(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState<ZoomLevel>("week");
  const [zoomPercent, setZoomPercent] = useState(100);
  const [mobilePane, setMobilePane] = useState<MobilePane>("timeline");
  const [riskFilter, setRiskFilter] = useState<GanttRiskLevel | null>(null);
  const [hoveredTaskId, setHoveredTaskId] = useState<string | null>(null);
  const [impact, setImpact] = useState<ScheduleImpact | null>(null);
  // Null while loading and for anyone the API will not show project-wide
  // predictions to; the chart simply omits the critical-path layer then.
  const [forecast, setForecast] = useState<ProjectForecast | null>(null);
  const [assignableUsers, setAssignableUsers] = useState<ProjectOwnerBrief[]>([]);
  const apiRef = useRef<IApi | null>(null);
  const chartRef = useRef<HTMLDivElement | null>(null);
  // Reloading remounts the Gantt so it picks up server-assigned link ids.
  const [reloadKey, setReloadKey] = useState(0);

  const loadForecast = useCallback(
    () =>
      fetchProjectForecast(projectId)
        .then(setForecast)
        .catch(() => setForecast(null)),
    [projectId],
  );

  const load = useCallback(async () => {
    try {
      const result = await fetchProjectGantt(projectId);
      setData(result);
      setReloadKey((value) => value + 1);
      void loadForecast();
      if (result.editable) {
        try {
          setAssignableUsers(await fetchAssignableUsers(projectId));
        } catch {
          setAssignableUsers([]);
        }
      } else {
        setAssignableUsers([]);
      }
    } catch {
      message.error("加载甘特图失败");
    } finally {
      setLoading(false);
    }
  }, [loadForecast, message, projectId]);

  useEffect(() => {
    void loadForecast();
  }, [loadForecast]);

  useEffect(() => {
    let cancelled = false;
    fetchProjectGantt(projectId)
      .then(async (result) => {
        if (cancelled) return;
        setData(result);
        setReloadKey((value) => value + 1);
        if (result.editable) {
          try {
            const candidates = await fetchAssignableUsers(projectId);
            if (!cancelled) setAssignableUsers(candidates);
          } catch {
            if (!cancelled) setAssignableUsers([]);
          }
        } else if (!cancelled) {
          setAssignableUsers([]);
        }
      })
      .catch(() => {
        if (!cancelled) message.error("加载甘特图失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [message, projectId]);

  const editable = data?.editable ?? false;
  const today = startOfToday();
  const panelTitle = data?.project_name?.trim() || "项目甘特图";
  const ownerOptions = useMemo<OwnerChoice[]>(
    () =>
      assignableUsers.map((user) => ({
        value: user.id,
        label: `${user.name} (${user.username})`,
      })),
    [assignableUsers],
  );

  const applyTaskPatch = useCallback((taskId: number, patch: Partial<ProjectGanttData["tasks"][number]>) => {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        tasks: prev.tasks.map((task) => (task.id === taskId ? { ...task, ...patch } : task)),
      };
    });
  }, []);

  const saveProgress = useCallback(
    async (taskId: number, progress: number) => {
      try {
        await updateTask(taskId, { progress_percent: progress });
        applyTaskPatch(taskId, { progress_percent: progress });
        apiRef.current?.exec("update-task", {
          id: taskId,
          task: { progress },
          inProgress: true,
        });
      } catch {
        message.error("保存进度失败");
        void load();
        throw new Error("progress_save_failed");
      }
    },
    [applyTaskPatch, load, message],
  );

  const saveOwner = useCallback(
    async (taskId: number, ownerId: number | null) => {
      const picked = ownerId == null ? null : assignableUsers.find((user) => user.id === ownerId);
      try {
        const updated = await updateTask(taskId, { owner_id: ownerId });
        applyTaskPatch(taskId, {
          owner_id: ownerId,
          owner: updated.owner ?? picked ?? undefined,
        });
      } catch {
        message.error("更换负责人失败");
        void load();
        throw new Error("owner_save_failed");
      }
    },
    [applyTaskPatch, assignableUsers, load, message],
  );

  /**
   * SVAR calls this with the smallest scale unit, so the today band has to be
   * resolved per zoom level: an exact day, or the week / month containing it.
   */
  const highlightTime = useCallback(
    (date: Date, unit: string): string => {
      if (unit === "day") {
        const classes: string[] = [];
        const day = date.getDay();
        if (day === 0 || day === 6) classes.push("wx-weekend");
        if (isSameDay(date, today)) classes.push("gantt-today-cell");
        return classes.join(" ");
      }

      const next = new Date(date);
      if (unit === "week") next.setDate(next.getDate() + 7);
      else if (unit === "month") next.setMonth(next.getMonth() + 1);
      else return "";
      return date <= today && today < next ? "gantt-today-cell" : "";
    },
    [today],
  );

  const riskCounts = useMemo(() => {
    const counts = Object.fromEntries(
      GANTT_RISK_ORDER.map((id) => [id, 0]),
    ) as Record<GanttRiskLevel, number>;
    for (const task of data?.tasks ?? []) {
      counts[resolveGanttRisk(task, today)] += 1;
    }
    return counts;
  }, [data, today]);

  const reportLinkFailure = useCallback(
    (error: unknown, fallback: string) => {
      const ripple = scheduleImpactOf(error);
      if (ripple) {
        setImpact(ripple);
      } else {
        const detail =
          error && typeof error === "object" && "payload" in error
            ? (error as { payload?: { detail?: string } }).payload?.detail
            : undefined;
        message.error(detail ?? fallback);
      }
      void load();
    },
    [load, message],
  );

  const init = useCallback(
    (api: IApi) => {
      apiRef.current = api;

      // Center on today after first paint. On narrow screens SVAR compact mode
      // may flip displayMode; re-assert the pane we want after layout.
      requestAnimationFrame(() => {
        if (isMobile) {
          api.exec("set-display-mode", {
            mode: mobilePane === "timeline" ? "chart" : "grid",
          });
        }
        api.exec("scroll-chart", { date: today });
      });

      // Disable drag-to-reschedule (move / resize bars). Progress & links stay editable.
      api.intercept("drag-task", (event) => {
        if (typeof event.left === "number" || typeof event.width === "number") {
          return false;
        }
      });
      api.intercept("update-task", (event) => {
        if (
          event.diff !== undefined ||
          event.task?.start !== undefined ||
          event.task?.end !== undefined
        ) {
          return false;
        }
      });

      if (!editable) return;

      api.on("update-task", (event) => {
        if (event.inProgress) return;
        // Section headers are synthetic rows with negative ids; they have no API resource.
        if (Number(event.id) < 0) return;

        const patch: Record<string, unknown> = {};

        if (typeof event.task.text === "string") {
          patch.task_name = event.task.text;
        }
        const progress = clampProgress(event.task.progress);
        if (progress !== undefined) {
          patch.progress_percent = progress;
        }
        if (Object.keys(patch).length === 0) return;

        void updateTask(Number(event.id), patch).catch(() => {
          message.error("保存任务变更失败，已恢复");
          void load();
        });
      });

      api.on("add-link", (event) => {
        const { link } = event;
        if (link.source === undefined || link.target === undefined) return;
        void createTaskLink(projectId, {
          source_id: Number(link.source),
          target_id: Number(link.target),
          link_type: fromSvarLinkType(link.type),
        })
          .then(() => load())
          .catch((error: unknown) => reportLinkFailure(error, "创建依赖失败"));
      });

      api.on("update-link", (event) => {
        void updateTaskLink(Number(event.id), fromSvarLinkType(event.link.type)).catch(
          (error: unknown) => reportLinkFailure(error, "更新依赖失败"),
        );
      });

      api.on("delete-link", (event) => {
        void deleteTaskLink(Number(event.id)).catch((error: unknown) =>
          reportLinkFailure(error, "删除依赖失败"),
        );
      });
    },
    [editable, isMobile, load, message, mobilePane, projectId, reportLinkFailure, today],
  );

  useEffect(() => {
    if (!isMobile || !apiRef.current) return;
    apiRef.current.exec("set-display-mode", {
      mode: mobilePane === "timeline" ? "chart" : "grid",
    });
  }, [isMobile, mobilePane, reloadKey]);

  const rows = useMemo(() => {
    if (!data) return [];
    // Inactive branches stay off the chart so alternate routes don't clutter the plan.
    const active = data.tasks.filter((task) => task.is_active_branch !== false);
    const source = riskFilter
      ? active.filter((task) => resolveGanttRisk(task, today) === riskFilter)
      : active;
    return toSvarRows(source, today);
  }, [data, riskFilter, today]);

  const taskIds = useMemo(
    () => new Set(rows.filter((row) => !row.is_group).map((row) => Number(row.id))),
    [rows],
  );

  const links = useMemo(() => {
    if (!data) return [];
    return data.links
      .filter((link) => taskIds.has(link.source_id) && taskIds.has(link.target_id))
      .map(toSvarLink);
  }, [data, taskIds]);

  /** Left-hand grid mirrors the Excel tracker's six columns, plus 状态. */
  const columns = useMemo(() => {
    const nameCol = {
      id: "text",
      header: "任务名称",
      width: isMobile ? (mobilePane === "timeline" ? 148 : 200) : 216,
      resize: !isMobile,
      cell: ({ row }: { row: GanttRow }) =>
        row.is_group ? (
          <span className="gantt-group-cell">
            {row.text ?? ""}
            <span className="gantt-group-cell__count">{row.task_count ?? 0}</span>
          </span>
        ) : (
          <span className="gantt-name-cell">{row.text ?? ""}</span>
        ),
    };
    if (isMobile && mobilePane === "timeline") {
      return [nameCol];
    }
    const compact = [
      nameCol,
      {
        id: "risk_level",
        header: "类别",
        width: 74,
        align: "center" as const,
        resize: !isMobile,
        cell: ({ row }: { row: GanttRow }) => {
          if (row.is_group) return "";
          const meta = GANTT_RISK_META[row.risk_level ?? "low_risk"];
          return (
            <span
              className="gantt-risk-chip"
              style={{ background: meta.color, color: meta.onColor }}
            >
              {meta.label}
            </span>
          );
        },
      },
      {
        id: "visual_status",
        header: "状态",
        width: 68,
        align: "center" as const,
        resize: !isMobile,
        cell: ({ row }: { row: GanttRow }) => {
          if (row.is_group) return "";
          const visual = row.visual_status ?? "not_started";
          return (
            <span className={`gantt-status-badge gantt-status-badge--${visual}`}>
              {GANTT_STATUS_META[visual].label}
            </span>
          );
        },
      },
    ];
    if (isMobile) {
      return compact;
    }
    return [
      ...compact,
      {
        id: "owner",
        header: "负责人",
        width: 100,
        align: "center" as const,
        resize: true,
        cell: ({ row }: { row: GanttRow }) => (
          <OwnerEditCell
            row={row}
            editable={editable && ownerOptions.length > 0}
            options={ownerOptions}
            onCommit={saveOwner}
          />
        ),
      },
      {
        id: "progress",
        header: "进度",
        width: 82,
        align: "center" as const,
        resize: true,
        cell: ({ row }: { row: GanttRow }) => (
          <ProgressEditCell row={row} editable={editable} onCommit={saveProgress} />
        ),
      },
      {
        id: "start",
        header: "开始",
        width: 56,
        align: "center" as const,
        resize: true,
        cell: ({ row }: { row: GanttRow }) =>
          row.is_group || !row.start ? "" : `${row.start.getMonth() + 1}/${row.start.getDate()}`,
      },
      {
        id: "days",
        header: "天数",
        width: 54,
        align: "center" as const,
        resize: true,
        cell: ({ row }: { row: GanttRow }) => (row.is_group ? "" : (row.days ?? "")),
      },
      {
        id: "float",
        header: "机动",
        width: 62,
        align: "center" as const,
        resize: true,
        cell: ({ row }: { row: GanttRow }) => {
          if (row.is_group) return "";
          const slack = forecast?.floats?.[String(row.id)];
          if (!slack) return "—";
          if (slack.critical) return <span className="gantt-critical-chip">关键</span>;
          return slack.total_float_workdays === null ? "—" : `${slack.total_float_workdays} 天`;
        },
      },
    ];
  }, [editable, forecast, isMobile, mobilePane, ownerOptions, saveOwner, saveProgress]);

  const gridWidth = isMobile
    ? mobilePane === "timeline"
      ? GRID_WIDTH_MOBILE_TIMELINE
      : GRID_WIDTH_MOBILE_LIST
    : GRID_WIDTH_DESKTOP;

  // SVAR enters compact mode below ~650px and then only shows grid OR chart,
  // never both. Drive that mode from our mobile toggle so the timeline is
  // visible by default instead of a full-width task grid with chartWidth=0.
  const displayMode = isMobile ? (mobilePane === "timeline" ? "chart" : "grid") : "all";

  const cellWidth = Math.round((CELL_WIDTH[zoom] * zoomPercent) / 100);

  const relatedLinkIds = useMemo(() => {
    if (!hoveredTaskId || !data) return null;
    const id = Number(hoveredTaskId);
    const set = new Set<string>();
    for (const link of data.links) {
      if (link.source_id === id || link.target_id === id) {
        set.add(String(link.id));
      }
    }
    return set;
  }, [hoveredTaskId, data]);

  useEffect(() => {
    const root = chartRef.current;
    if (!root) return;
    const critical = new Set((forecast?.critical_task_ids ?? []).map(String));
    root.querySelectorAll<HTMLElement>(".wx-bar").forEach((bar) => {
      const id = bar.getAttribute("data-id") ?? bar.getAttribute("data-task-id");
      bar.classList.toggle("is-critical", Boolean(id) && critical.has(String(id)));
    });
  }, [forecast, reloadKey, rows.length, zoom, zoomPercent]);

  useEffect(() => {
    const root = chartRef.current;
    if (!root) return;
    const lines = root.querySelectorAll<SVGGElement>(".wx-line");
    lines.forEach((line) => {
      const linkId = line.getAttribute("data-link-id");
      line.classList.remove("is-related", "is-dimmed");
      if (!relatedLinkIds || !linkId) return;
      if (relatedLinkIds.has(linkId)) {
        line.classList.add("is-related");
      } else {
        line.classList.add("is-dimmed");
      }
    });
  }, [relatedLinkIds, reloadKey, rows.length]);

  const onChartPointer = (event: ReactMouseEvent<HTMLDivElement>) => {
    const bar = (event.target as Element | null)?.closest?.(".wx-bar");
    const id = bar?.getAttribute("data-id") ?? bar?.getAttribute("data-task-id") ?? null;
    setHoveredTaskId(id);
  };

  const clearHover = () => setHoveredTaskId(null);

  const toggleFilter = (risk: GanttRiskLevel) => {
    setRiskFilter((prev) => (prev === risk ? null : risk));
  };

  const scrollByPage = (dir: -1 | 1) => {
    const api = apiRef.current;
    if (!api) return;
    const state = api.getState();
    const page = Math.max(240, Math.round((state._chartWidth ?? 640) * 0.7));
    api.exec("scroll-chart", { left: (state.scrollLeft ?? 0) + page * dir });
  };

  const scrollToToday = () => {
    apiRef.current?.exec("scroll-chart", { date: today });
  };

  const changeZoomPercent = (delta: number) => {
    setZoomPercent((prev) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, prev + delta)));
  };

  if (loading) {
    return (
      <div className="gantt-panel gantt-panel--compact" style={{ height: 360 }}>
        <LoadingState tip="加载甘特图…" />
      </div>
    );
  }

  if (!data || data.tasks.length === 0) {
    return (
      <div className="gantt-panel gantt-panel--compact" style={{ height: 360 }}>
        <div className="gantt-panel__header">
          <div className="gantt-panel__header-left">
            <h2 className="gantt-panel__title">{panelTitle}</h2>
          </div>
          <div className="gantt-panel__header-right">
            {onClose ? (
              <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} aria-label="关闭" />
            ) : null}
          </div>
        </div>
        <EmptyState title="暂无任务" description="创建任务后即可生成甘特图。" />
      </div>
    );
  }

  return (
    <div
      className={`gantt-panel${isMobile ? ` gantt-panel--mobile gantt-panel--${mobilePane}` : ""}`}
    >
      <header className="gantt-panel__header">
        <div className="gantt-panel__header-left">
          <h2 className="gantt-panel__title" title={panelTitle}>
            {panelTitle}
          </h2>
          <Tooltip title={editable ? HELP_TEXT : "当前为只读视图，仅可浏览。"}>
            <button type="button" className="gantt-panel__help" aria-label="操作说明">
              <QuestionCircleOutlined />
            </button>
          </Tooltip>
          {riskFilter ? (
            <button type="button" className="gantt-panel__filter-chip" onClick={() => setRiskFilter(null)}>
              筛选：{GANTT_RISK_META[riskFilter].label} ×
            </button>
          ) : null}
          {forecast ? <ForecastNote forecast={forecast} /> : null}
        </div>
        <div className="gantt-panel__header-right">
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void load()}>
            刷新
          </Button>
          {onClose ? (
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} aria-label="关闭" />
          ) : null}
        </div>
      </header>

      <div className="gantt-panel__toolbar">
        {isMobile ? (
          <Segmented
            className="gantt-segmented"
            value={mobilePane}
            onChange={(value) => setMobilePane(value as MobilePane)}
            options={[
              { label: "时间轴", value: "timeline" },
              { label: "任务列", value: "list" },
            ]}
          />
        ) : null}
        <Segmented
          className="gantt-segmented"
          value={zoom}
          onChange={(value) => {
            setZoom(value as ZoomLevel);
            setZoomPercent(100);
          }}
          options={[
            { label: "日", value: "day" },
            { label: "周", value: "week" },
            { label: "月", value: "month" },
          ]}
        />

        <Space.Compact className="gantt-nav">
          <Button size="small" icon={<LeftOutlined />} onClick={() => scrollByPage(-1)} aria-label="向左" />
          <Button size="small" onClick={scrollToToday}>
            今天
          </Button>
          <Button size="small" icon={<RightOutlined />} onClick={() => scrollByPage(1)} aria-label="向右" />
        </Space.Compact>

        <div className="gantt-zoom">
          <Button
            size="small"
            icon={<MinusOutlined />}
            onClick={() => changeZoomPercent(-ZOOM_STEP)}
            disabled={zoomPercent <= ZOOM_MIN}
            aria-label="缩小"
          />
          <span className="gantt-zoom__label">{zoomPercent}%</span>
          <Button
            size="small"
            icon={<PlusOutlined />}
            onClick={() => changeZoomPercent(ZOOM_STEP)}
            disabled={zoomPercent >= ZOOM_MAX}
            aria-label="放大"
          />
        </div>
      </div>

      <GanttLegend
        active={riskFilter}
        onToggle={toggleFilter}
        counts={riskCounts}
        showCritical={(forecast?.critical_task_ids.length ?? 0) > 0}
      />

      {rows.length === 0 ? (
        <div className="gantt-panel__empty">
          <EmptyState
            title="无匹配任务"
            description="当前图例筛选下没有任务，请清除筛选或换一个类别。"
            action={
              <Button size="small" onClick={() => setRiskFilter(null)}>
                清除筛选
              </Button>
            }
          />
        </div>
      ) : (
        <div
          className={`gantt-panel__chart gantt-panel__chart--${zoom}`}
          ref={chartRef}
          onMouseOver={onChartPointer}
          onMouseLeave={clearHover}
          data-hover-task={hoveredTaskId ?? undefined}
          style={{ "--gantt-cell-width": `${cellWidth}px` } as CSSProperties}
        >
          <Willow fonts={false}>
            <Gantt
              key={`${zoom}-${reloadKey}-${riskFilter ?? "all"}-${zoomPercent}-${displayMode}`}
              init={init}
              tasks={rows}
              links={links}
              scales={SCALES[zoom]}
              columns={columns}
              taskTypes={GANTT_TASK_TYPES}
              highlightTime={highlightTime}
              cellWidth={cellWidth}
              cellHeight={ROW_HEIGHT}
              scaleHeight={SCALE_HEIGHT}
              gridWidth={gridWidth}
              displayMode={displayMode}
              readonly={!editable}
            />
          </Willow>
        </div>
      )}
      <ScheduleImpactModal
        projectId={projectId}
        impact={impact}
        onClose={() => setImpact(null)}
      />
    </div>
  );
}
