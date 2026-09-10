export type ProjectStatus = "PLANNING" | "ACTIVE" | "COMPLETED" | "CANCELLED";
export type ProjectRiskLevel = "NORMAL" | "AT_RISK" | "DELAYED";

export interface ProjectOwnerBrief {
  id: number;
  name: string;
  username: string;
}

export interface Project {
  id: number;
  project_code: string;
  project_name: string;
  goal: string | null;
  owner_id: number;
  start_date: string | null;
  target_date: string | null;
  status: ProjectStatus;
  risk_level: ProjectRiskLevel;
  created_at: string;
  updated_at: string;
  owner?: ProjectOwnerBrief | null;
  owners?: ProjectOwnerBrief[];
}

export interface ProjectCreateInput {
  project_code: string;
  project_name: string;
  goal?: string | null;
  owner_id: number;
  owner_ids?: number[];
  start_date?: string | null;
  target_date?: string | null;
  status?: ProjectStatus;
  risk_level?: ProjectRiskLevel;
}

export interface ProjectUpdateInput {
  project_name?: string;
  goal?: string | null;
  owner_id?: number;
  owner_ids?: number[];
  status?: ProjectStatus;
  risk_level?: ProjectRiskLevel;
}

export interface ProjectScheduleUpdateInput {
  start_date?: string | null;
  target_date?: string | null;
  change_reason: string;
}

export interface ProjectOwnersUpdateInput {
  owner_ids: number[];
}
