export type ActionItemStatus = "OPEN" | "IN_PROGRESS" | "DONE" | "CANCELLED";
export type ActionItemPriority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";

export interface ActionItemUserBrief {
  id: number;
  name: string;
  username: string;
}

export interface ActionItem {
  id: number;
  project_id: number;
  task_id: number | null;
  issue_id: number | null;
  owner_id: number | null;
  created_by: number;
  title: string;
  description: string | null;
  due_date: string | null;
  status: ActionItemStatus;
  priority: ActionItemPriority;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  owner?: ActionItemUserBrief | null;
  creator?: ActionItemUserBrief | null;
  task?: { id: number; task_name: string } | null;
  issue?: { id: number; title: string } | null;
}

export const OPEN_ACTION_ITEM_STATUSES: ActionItemStatus[] = ["OPEN", "IN_PROGRESS"];

export function isActionItemOpen(item: ActionItem): boolean {
  return OPEN_ACTION_ITEM_STATUSES.includes(item.status);
}
