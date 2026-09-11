export type RiskEventType = "OVERDUE" | "FORECAST_DELAY" | "ISSUE" | "MISSING_DATA";
export type RiskEventLevel = "AT_RISK" | "DELAYED";
export type RiskEventStatus = "OPEN" | "RESOLVED";

export interface RiskEvidence {
  source_type: string;
  source_id: number | null;
  updated_at: string | null;
  detail: string;
  /** Why this record was selected. Only present on advice evidence. */
  relevance?: string;
}

export interface RiskEvent {
  id: number;
  project_id: number;
  task_id: number | null;
  issue_id: number | null;
  event_type: RiskEventType;
  level: RiskEventLevel;
  status: RiskEventStatus;
  title: string;
  cause: string;
  evidence: RiskEvidence[];
  /** The date the risk bites: a due date, or a predicted finish date. */
  impact_date: string | null;
  impact_days: number | null;
  owner_id: number | null;
  owner_name: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
}

export interface RiskSummary {
  total: number;
  OVERDUE: number;
  FORECAST_DELAY: number;
  ISSUE: number;
  MISSING_DATA: number;
}

export const RISK_TYPE_LABELS: Record<RiskEventType, string> = {
  OVERDUE: "事实逾期",
  FORECAST_DELAY: "预测交付风险",
  ISSUE: "问题风险",
  MISSING_DATA: "信息缺失",
};

/** What each type does and does not claim, shown next to the record. */
export const RISK_TYPE_MEANING: Record<RiskEventType, string> = {
  OVERDUE: "计划日期已过且未完成，是已发生的事实。",
  FORECAST_DELAY: "按当前计划推算晚于目标日期。这是预测，目标日期本身没有变。",
  ISSUE: "存在未解决的高严重度问题，可能影响交付。",
  MISSING_DATA: "数据不足以做出判断，不等于没有风险。",
};

export const RISK_LEVEL_COLORS: Record<RiskEventLevel, string> = {
  AT_RISK: "orange",
  DELAYED: "red",
};

export const RISK_LEVEL_LABELS: Record<RiskEventLevel, string> = {
  AT_RISK: "有风险",
  DELAYED: "已延期",
};
