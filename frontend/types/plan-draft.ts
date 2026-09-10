export type PlanDraftStatus = "DRAFT" | "REVIEWED" | "PUBLISHED" | "DISCARDED" | "FAILED";

export interface DraftTask {
  client_id: number;
  task_name: string;
  owner_id: number | null;
  work_stream?: string | null;
  description?: string | null;
  deliverable?: string | null;
  acceptance_criteria?: string | null;
  start_date: string | null;
  due_date: string | null;
  planned_duration_days: number | null;
  earliest_start_date?: string | null;
  fixed_start_date?: string | null;
  fixed_due_date?: string | null;
  milestone_client_id: number | null;
  estimate_basis: string | null;
}

export interface DraftLink {
  source_client_id: number;
  target_client_id: number;
  link_type: string;
  lag_days: number;
}

export interface DraftMilestone {
  client_id: number;
  name: string;
  target_date: string | null;
  deliverable?: string | null;
  acceptance_criteria?: string | null;
}

export interface PlanDraftContent {
  project: {
    project_code: string;
    project_name: string;
    goal: string | null;
    owner_id: number | null;
    owner_ids: number[] | null;
    start_date: string | null;
    target_date: string | null;
  };
  tasks: DraftTask[];
  links: DraftLink[];
  milestones: DraftMilestone[];
  assumptions: string[];
  open_questions: string[];
}

export interface PlanDraftReview {
  blocking: string[];
  warnings: string[];
  task_count: number;
  link_count: number;
  milestone_count: number;
  assumptions: string[];
  publishable: boolean;
  checked_at: string;
}

export interface PlanDraft {
  id: string;
  created_by: number;
  created_by_name: string;
  title: string;
  status: PlanDraftStatus;
  revision: number;
  content: PlanDraftContent;
  review: PlanDraftReview | null;
  digest: string | null;
  project_id: number | null;
  published_at: string | null;
  result: {
    project_id: number;
    project_code: string;
    task_id_map: Record<string, number>;
    milestone_id_map: Record<string, number>;
    link_count: number;
    plan_version_id: number;
  } | null;
  failure_reason: string | null;
  created_at: string;
}

export const PLAN_DRAFT_STATUS_LABELS: Record<PlanDraftStatus, string> = {
  DRAFT: "草稿",
  REVIEWED: "已校验待发布",
  PUBLISHED: "已发布",
  DISCARDED: "已废弃",
  FAILED: "发布失败",
};
