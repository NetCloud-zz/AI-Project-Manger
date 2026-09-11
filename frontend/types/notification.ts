export type NotificationStatus = "QUEUED" | "SENT" | "FAILED" | "ACKNOWLEDGED";

export interface NotificationTaskChange {
  task_id: number;
  task_name: string | null;
  is_new?: boolean;
  before_start_date?: string | null;
  before_due_date?: string | null;
  start_date: string | null;
  due_date: string | null;
  status?: string | null;
  owner_id?: number | null;
}

export type NotificationEventType =
  | "PLAN_CHANGE"
  | "RISK_OPENED"
  | "RISK_ESCALATED"
  | "RISK_RESOLVED";

/** The risk behind a RISK_* notification, copied at the time it was queued. */
export interface NotificationRisk {
  risk_type: "OVERDUE" | "FORECAST_DELAY" | "ISSUE" | "MISSING_DATA";
  level: "AT_RISK" | "DELAYED";
  previous_level: string | null;
  title: string | null;
  cause: string | null;
  task_id: number | null;
  issue_id: number | null;
  impact_date: string | null;
  impact_days: number | null;
  resolution: string | null;
  /** A forecast is a prediction; everything else here already happened. */
  is_prediction: boolean;
  kind_note: string | null;
}

export interface PlanNotification {
  id: number;
  proposal_id: string | null;
  project_id: number;
  project_code: string | null;
  project_name: string | null;
  recipient_id: number;
  recipient_name: string;
  event_type: NotificationEventType;
  channel: string;
  /** Console output is a local simulation, not a real send. */
  simulated: boolean;
  status: NotificationStatus;
  attempts: number;
  last_error: string | null;
  /** The channel never answered; the message may or may not have arrived. */
  delivery_uncertain: boolean;
  created_at: string | null;
  next_attempt_at: string | null;
  sent_at: string | null;
  acknowledged_at: string | null;
  can_acknowledge: boolean;
  reason: string | null;
  operator_name: string | null;
  project: { before: { target_date: string | null }; after: { target_date: string | null } } | null;
  forecast_finish_date: string | null;
  tasks: NotificationTaskChange[];
  risk_event_id: number | null;
  risk: NotificationRisk | null;
}

export const NOTIFICATION_EVENT_LABELS: Record<NotificationEventType, string> = {
  PLAN_CHANGE: "计划变更",
  RISK_OPENED: "风险提醒",
  RISK_ESCALATED: "风险升级",
  RISK_RESOLVED: "风险解除",
};

export const NOTIFICATION_EVENT_COLORS: Record<NotificationEventType, string> = {
  PLAN_CHANGE: "blue",
  RISK_OPENED: "orange",
  RISK_ESCALATED: "red",
  RISK_RESOLVED: "green",
};

export const NOTIFICATION_STATUS_LABELS: Record<NotificationStatus, string> = {
  QUEUED: "待发送",
  SENT: "渠道已接受",
  FAILED: "发送失败",
  ACKNOWLEDGED: "已确认知悉",
};

export const NOTIFICATION_STATUS_COLORS: Record<NotificationStatus, string> = {
  QUEUED: "default",
  SENT: "blue",
  FAILED: "red",
  ACKNOWLEDGED: "green",
};
