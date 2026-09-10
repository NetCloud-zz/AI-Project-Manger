import { request } from "@/lib/http";
import type { ActionItem, ActionItemPriority, ActionItemStatus } from "@/types/action_item";

export type ActionItemCreateInput = {
  title: string;
  description?: string | null;
  owner_id?: number | null;
  task_id?: number | null;
  issue_id?: number | null;
  due_date?: string | null;
  status?: ActionItemStatus;
  priority?: ActionItemPriority;
};

export type ActionItemUpdateInput = Partial<ActionItemCreateInput>;

export async function fetchProjectActionItems(
  projectId: number,
  params?: { openOnly?: boolean; status?: ActionItemStatus },
): Promise<ActionItem[]> {
  const search = new URLSearchParams();
  if (params?.openOnly) search.set("open_only", "true");
  if (params?.status) search.set("status", params.status);
  const qs = search.toString();
  return request<ActionItem[]>(
    `/api/v1/projects/${projectId}/action-items${qs ? `?${qs}` : ""}`,
    { cache: "no-store" },
  );
}

export async function fetchMyActionItems(ownerId: number): Promise<ActionItem[]> {
  return request<ActionItem[]>(`/api/v1/action-items?owner_id=${ownerId}&open_only=true`, {
    cache: "no-store",
  });
}

export async function createProjectActionItem(
  projectId: number,
  body: ActionItemCreateInput,
): Promise<ActionItem> {
  return request<ActionItem>(`/api/v1/projects/${projectId}/action-items`, {
    method: "POST",
    body,
  });
}

export async function updateActionItem(
  actionItemId: number,
  body: ActionItemUpdateInput,
): Promise<ActionItem> {
  return request<ActionItem>(`/api/v1/action-items/${actionItemId}`, {
    method: "PATCH",
    body,
  });
}
