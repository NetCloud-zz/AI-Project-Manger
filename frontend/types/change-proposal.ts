export interface ProposalRequest {
  [key: string]: unknown;
  changes?: Record<string, unknown>[];
  new_tasks?: { client_id: number; task: Record<string, unknown> }[];
  links?: { source_id: number; target_id: number; link_type: string; lag_days: number }[];
  selections?: { group_id: number; option_id: number }[];
}
export interface ChangeProposal {
  id: string;
  revision: number;
  status: "DRAFT" | "VALIDATED" | "CONFIRMED" | "APPLIED" | "REJECTED" | "EXPIRED" | "FAILED";
  reason: string;
  request: ProposalRequest;
  digest: string | null;
  confirmed_by: number | null;
  applied_version_id: number | null;
  created_at: string;
  expires_at: string | null;
  failure_reason: string | null;
  preview?: { candidate: { feasible: boolean; project_finish_date: string | null; conflicts: { message: string; suggestion: string }[] } } | null;
  diff: {
    tasks: { task_id: number; before: Record<string, unknown> | null; after: Record<string, unknown> }[];
    project: { before: { target_date: string | null }; after: { target_date: string | null } } | null;
    links: { before: { source_id: number; target_id: number; link_type: string; lag_days: number }[]; after: { source_id: number; target_id: number; link_type: string; lag_days: number }[] };
    selections: { group_id: number; before_option_id: number | null; after_option_id: number }[];
    notifications: { user_id: number; task_ids: number[] }[];
  } | null;
}
