/**
 * The plan's predicted finish date and critical path.
 *
 * Everything here is a prediction produced by the schedule engine from the
 * current plan. It never changes the committed target date, and the UI is
 * expected to keep that distinction visible.
 */

export type ForecastVerdict = "ON_TRACK" | "BEHIND" | "NO_TARGET" | "UNKNOWN";

export interface ForecastDiagnostic {
  code: string;
  message: string;
  task_ids: number[];
  suggestion: string;
}

export interface CriticalPathStep {
  task_id: number;
  task_name: string;
  status: string;
  start_date: string;
  finish_date: string;
  total_float_workdays: number | null;
}

export interface TaskFloat {
  predicted_start_date: string;
  predicted_finish_date: string;
  total_float_workdays: number | null;
  free_float_workdays: number | null;
  critical: boolean;
}

export interface ProjectForecast {
  project_id: number;
  as_of: string;
  /** False when the graph or the data will not yield a date at all. */
  computable: boolean;
  verdict: ForecastVerdict;
  predicted_finish_date: string | null;
  target_date: string | null;
  variance_workdays: number | null;
  variance_calendar_days: number | null;
  critical_task_ids: number[];
  critical_path: CriticalPathStep[];
  /** Keyed by task id as a string, because it arrives as a JSON object. */
  floats: Record<string, TaskFloat>;
  conflicts: ForecastDiagnostic[];
  warnings: ForecastDiagnostic[];
  excluded_task_ids: number[];
  calendar_version: number;
  notices: string[];
}

export const FORECAST_VERDICT_LABELS: Record<ForecastVerdict, string> = {
  ON_TRACK: "预测可按期完成",
  BEHIND: "预测晚于目标日期",
  NO_TARGET: "尚未设定目标日期",
  UNKNOWN: "当前数据算不出预测",
};

export const FORECAST_VERDICT_COLORS: Record<ForecastVerdict, string> = {
  ON_TRACK: "green",
  BEHIND: "red",
  NO_TARGET: "default",
  UNKNOWN: "orange",
};
