export interface ProgressUpdate {
  id: number;
  task_id: number;
  user_id: number;
  raw_content: string;
  summary: string | null;
  progress_percent: number | null;
  ai_status: string | null;
  risk_detected: boolean | null;
  ai_analysis_failed: boolean;
  created_at: string;
}

export interface ProgressSubmitInput {
  content: string;
  mark_completed?: boolean;
}

export interface RecentProgressItem {
  id: number;
  task_id: number;
  task_name: string;
  user_id: number;
  user_name: string;
  raw_content: string;
  summary: string | null;
  created_at: string;
}
