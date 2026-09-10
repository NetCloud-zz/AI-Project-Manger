export type ProjectStatus = "PLANNING" | "ACTIVE" | "COMPLETED" | "CANCELLED";
export type ProjectRiskLevel = "NORMAL" | "AT_RISK" | "DELAYED";

export interface DashboardProjectItem {
  project_id: number;
  project_code: string;
  project_name: string;
  status: ProjectStatus;
  risk_level: ProjectRiskLevel;
  owner: string;
  current_focus: string | null;
  next_deadline: string | null;
}

export interface ManagementDashboard {
  project_total: number;
  normal_count: number;
  at_risk_count: number;
  delayed_count: number;
  project_items: DashboardProjectItem[];
  management_attention_count: number;
}

export interface PersonalDashboard {
  my_active_tasks: number;
  my_overdue_tasks: number;
}

export type DashboardData = ManagementDashboard | PersonalDashboard;

export function isManagementDashboard(data: DashboardData): data is ManagementDashboard {
  return "project_total" in data;
}
