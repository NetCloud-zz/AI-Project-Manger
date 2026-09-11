import type { Task } from "@/types/task";

export interface Member {
  project_id: number; user_id: number; user_name: string;
  role: "CONTRIBUTOR" | "OBSERVER"; receive_notifications: boolean; is_active: boolean;
}
export interface Participant { user_id: number; user_name?: string; role: "COLLABORATOR" | "WATCHER" }
export interface Calendar {
  project_id: number; name: string; timezone: string; weekdays: number[];
  exceptions: Record<string, boolean>; version: number;
}
export interface Milestone {
  id: number; name: string; deliverable: string | null; acceptance_criteria: string | null;
  target_date: string | null; owner_id: number | null; status: "PLANNED" | "ACHIEVED" | "CANCELLED";
  achieved_date: string | null;
}
export interface TaskGroup { id: number; name: string; parent_id: number | null }
export interface BranchGroup { id: number; name: string; entry_task_id: number | null; exit_task_id: number | null }
export interface BranchOption { id: number; group_id: number; name: string; is_selected: boolean; task_ids: number[] }
export interface PlanVersion { id: number; version: number; kind: string; reason: string; created_at: string; snapshot?: Record<string, unknown> }
export interface PlanningContext {
  project_id: number; editable: boolean; full_access: boolean; calendar: Calendar;
  tasks: Task[]; members: Member[]; milestones: Milestone[]; task_groups: TaskGroup[];
  branch_groups: BranchGroup[]; branch_options: BranchOption[]; versions: PlanVersion[];
  links: { id: number; source_id: number; target_id: number; link_type: string; lag_days: number }[];
}
