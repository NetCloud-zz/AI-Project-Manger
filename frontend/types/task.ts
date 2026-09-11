export interface TaskPlanningFields {
  description?: string | null;
  deliverable?: string | null;
  acceptance_criteria?: string | null;
  planned_duration_days?: number | null;
  remaining_duration_days?: number | null;
  actual_start_date?: string | null;
  actual_finish_date?: string | null;
  earliest_start_date?: string | null;
  fixed_start_date?: string | null;
  fixed_due_date?: string | null;
  calendar_id?: number | null;
  milestone_id?: number | null;
  task_group_id?: number | null;
}

export type TaskStatus = "TODO" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
export type TaskAiStatus = "ON_TRACK" | "AT_RISK" | "DELAYED";

export interface TaskOwnerBrief {
  id: number;
  name: string;
  username: string;
}

export interface TaskProjectBrief {
  id: number;
  project_code: string;
  project_name: string;
}

export interface Task extends TaskPlanningFields {
  branch_option_id?: number | null;
  id: number;
  project_id: number;
  task_name: string;
  /** Work stream / phase used to group rows in the Gantt view. */
  work_stream: string | null;
  owner_id: number;
  start_date: string | null;
  due_date: string | null;
  progress_percent: number | null;
  status: TaskStatus;
  ai_status: TaskAiStatus | null;
  ai_risk_level: TaskAiStatus | null;
  completed_at: string | null;
  branch_root_id: number | null;
  branch_label: string | null;
  is_active_branch: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  owner?: TaskOwnerBrief | null;
  project?: TaskProjectBrief | null;
}

export interface TaskCreateInput extends TaskPlanningFields {
  task_name: string;
  work_stream?: string | null;
  owner_id: number;
  start_date?: string | null;
  due_date?: string | null;
  progress_percent?: number | null;
  status?: TaskStatus;
}

export interface TaskUpdateInput extends TaskPlanningFields {
  task_name?: string;
  work_stream?: string | null;
  owner_id?: number;
  start_date?: string | null;
  due_date?: string | null;
  progress_percent?: number | null;
  status?: TaskStatus;
  /** When set, must match the current task.version or the API returns 409. */
  expected_version?: number;
}

export interface TaskBranchCreateInput {
  task_name: string;
  branch_label: string;
  owner_id?: number | null;
  start_date?: string | null;
  due_date?: string | null;
  work_stream?: string | null;
  activate?: boolean;
  reason: string;
}

export interface TaskBranchActivateInput {
  reason: string;
}
