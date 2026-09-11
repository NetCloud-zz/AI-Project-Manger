export interface ScheduleDiagnostic {
  code: string;
  message: string;
  task_ids: number[];
  suggestion: string;
}

export interface ScheduledTask {
  task_id: number;
  task_name: string;
  status: string;
  start_date: string;
  finish_date: string;
  actual_start_date: string | null;
  actual_finish_date: string | null;
  total_float_workdays: number | null;
  network_float_workdays: number | null;
  free_float_workdays: number | null;
  critical: boolean;
}

export interface ScheduleResult {
  feasible: boolean;
  tasks: ScheduledTask[];
  conflicts: ScheduleDiagnostic[];
  warnings: ScheduleDiagnostic[];
  project_finish_date: string | null;
  target_variance_workdays: number | null;
  target_variance_calendar_days: number | null;
  critical_task_ids: number[];
  critical_path: number[];
}

export interface SchedulePreview {
  as_of: string;
  current_target_date: string | null;
  proposed_target_date: string | null;
  snapshot_token: string;
  calendar_version: number;
  read_only: true;
  baseline: { version: number; kind: string; created_at: string } | null;
  current: ScheduleResult;
  candidate: ScheduleResult;
  changes: {
    task_id: number;
    task_name: string;
    baseline_start_date: string | null;
    baseline_due_date: string | null;
    current_start_date: string | null;
    current_due_date: string | null;
    predicted_start_date: string;
    predicted_finish_date: string;
    finish_delta_workdays: number | null;
  }[];
  branch_dispositions: { task_id: number; from_status: string; to_status: string; reason: string }[];
  excluded_task_ids: number[];
  forecast_delta_workdays: number | null;
  notices: string[];
}
