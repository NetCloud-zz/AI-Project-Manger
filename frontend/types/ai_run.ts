export type AIRunType =
  | "PROGRESS_ANALYSIS"
  | "ISSUE_ADVICE"
  | "DAILY_SUMMARY"
  | "CONVERSATION_SUMMARY";

export type AIRunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "DISABLED";

export interface AIRun {
  id: number;
  run_type: AIRunType;
  resource_type: string;
  resource_id: string;
  status: AIRunStatus;
  model: string | null;
  error_code: string | null;
  user_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
