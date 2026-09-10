import type { Task } from "@/types/task";

export type TaskLinkType =
  | "FINISH_TO_START"
  | "START_TO_START"
  | "FINISH_TO_FINISH"
  | "START_TO_FINISH";

export interface TaskLink {
  id: number;
  project_id: number;
  source_id: number;
  target_id: number;
  link_type: TaskLinkType;
  lag_days?: number;
}

export interface ProjectGanttData {
  project_id: number;
  project_code: string;
  project_name: string;
  target_date: string | null;
  editable: boolean;
  tasks: Task[];
  links: TaskLink[];
}

export interface TaskLinkCreateInput {
  source_id: number;
  target_id: number;
  link_type?: TaskLinkType;
  lag_days?: number;
}
