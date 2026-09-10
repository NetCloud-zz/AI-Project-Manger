import { Tag } from "antd";

const PROJECT_STATUS: Record<string, { color: string; label: string }> = {
  PLANNING: { color: "default", label: "规划中" },
  ACTIVE: { color: "processing", label: "进行中" },
  COMPLETED: { color: "success", label: "已完成" },
  CANCELLED: { color: "default", label: "已取消" },
};

const TASK_STATUS: Record<string, { color: string; label: string }> = {
  TODO: { color: "default", label: "待办" },
  IN_PROGRESS: { color: "processing", label: "进行中" },
  COMPLETED: { color: "success", label: "已完成" },
  CANCELLED: { color: "default", label: "已取消" },
};

const RISK: Record<string, { color: string; label: string }> = {
  NORMAL: { color: "green", label: "正常" },
  AT_RISK: { color: "orange", label: "有风险" },
  DELAYED: { color: "red", label: "已延期" },
};

const ISSUE_STATUS: Record<string, { color: string; label: string }> = {
  OPEN: { color: "error", label: "待处理" },
  IN_PROGRESS: { color: "processing", label: "处理中" },
  RESOLVED: { color: "success", label: "已解决" },
};

const ISSUE_SEVERITY: Record<string, { color: string; label: string }> = {
  LOW: { color: "default", label: "低" },
  MEDIUM: { color: "orange", label: "中" },
  HIGH: { color: "red", label: "高" },
  CRITICAL: { color: "red", label: "严重" },
};

const ACTION_ITEM_STATUS: Record<string, { color: string; label: string }> = {
  OPEN: { color: "warning", label: "待处理" },
  IN_PROGRESS: { color: "processing", label: "进行中" },
  DONE: { color: "success", label: "已完成" },
  CANCELLED: { color: "default", label: "已取消" },
};

const ACTION_ITEM_PRIORITY: Record<string, { color: string; label: string }> = {
  LOW: { color: "default", label: "低" },
  MEDIUM: { color: "blue", label: "中" },
  HIGH: { color: "orange", label: "高" },
  URGENT: { color: "red", label: "紧急" },
};

function toOptions(source: Record<string, { label: string }>) {
  return Object.entries(source).map(([value, meta]) => ({ value, label: meta.label }));
}

/** Filter dropdowns reuse these so labels never drift from the tags. */
export const PROJECT_STATUS_OPTIONS = toOptions(PROJECT_STATUS);
export const TASK_STATUS_OPTIONS = toOptions(TASK_STATUS);
export const RISK_OPTIONS = toOptions(RISK);
export const ISSUE_STATUS_OPTIONS = toOptions(ISSUE_STATUS);
export const ISSUE_SEVERITY_OPTIONS = toOptions(ISSUE_SEVERITY);
export const ACTION_ITEM_STATUS_OPTIONS = toOptions(ACTION_ITEM_STATUS);
export const ACTION_ITEM_PRIORITY_OPTIONS = toOptions(ACTION_ITEM_PRIORITY);

export function ProjectStatusTag({ status }: { status: string }) {
  const meta = PROJECT_STATUS[status] ?? { color: "default", label: status };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function TaskStatusTag({ status }: { status: string }) {
  const meta = TASK_STATUS[status] ?? { color: "default", label: status };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function RiskTag({ level }: { level: string }) {
  const meta = RISK[level] ?? { color: "default", label: level };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function IssueStatusTag({ status }: { status: string }) {
  const meta = ISSUE_STATUS[status] ?? { color: "default", label: status };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function IssueSeverityTag({ severity }: { severity: string }) {
  const meta = ISSUE_SEVERITY[severity] ?? { color: "default", label: severity };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function ActionItemStatusTag({ status }: { status: string }) {
  const meta = ACTION_ITEM_STATUS[status] ?? { color: "default", label: status };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

export function ActionItemPriorityTag({ priority }: { priority: string }) {
  const meta = ACTION_ITEM_PRIORITY[priority] ?? { color: "default", label: priority };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}
