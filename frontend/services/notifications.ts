import { request } from "@/lib/http";
import type { NotificationStatus, PlanNotification } from "@/types/notification";

export function listMyNotifications(params?: {
  status?: NotificationStatus;
  limit?: number;
}): Promise<PlanNotification[]> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.limit != null) search.set("limit", String(params.limit));
  const qs = search.toString();
  return request<PlanNotification[]>(`/api/v1/notifications${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
}

export function acknowledgeNotification(eventId: number): Promise<PlanNotification> {
  return request<PlanNotification>(`/api/v1/notifications/${eventId}/acknowledge`, {
    method: "POST",
  });
}

export function retryNotification(eventId: number): Promise<PlanNotification> {
  return request<PlanNotification>(`/api/v1/notifications/${eventId}/retry`, {
    method: "POST",
  });
}

export function listProposalNotifications(
  projectId: number,
  proposalId: string,
): Promise<PlanNotification[]> {
  return request<PlanNotification[]>(
    `/api/v1/projects/${projectId}/planning/change-proposals/${proposalId}/notifications`,
    { cache: "no-store" },
  );
}
