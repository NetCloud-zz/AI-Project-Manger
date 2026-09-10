export type IssueSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type IssueStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED";

export interface Issue {
  id: number;
  project_id: number;
  /** Null for problems logged at project level without an owning task. */
  task_id: number | null;
  reported_by: number;
  title: string;
  description: string;
  severity: IssueSeverity;
  status: IssueStatus;
  suggested_solution: string | null;
  suggested_solution_is_ai?: boolean;
  created_at: string;
  resolved_at: string | null;
  task?: { id: number; task_name: string } | null;
  reporter?: { id: number; name: string; username: string } | null;
}

export const OPEN_ISSUE_STATUSES: IssueStatus[] = ["OPEN", "IN_PROGRESS"];
