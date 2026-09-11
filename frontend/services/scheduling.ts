import { request } from "@/lib/http";
import type { SchedulePreview } from "@/types/scheduling";

export function previewSchedule(projectId: number, body: unknown): Promise<SchedulePreview> {
  return request<SchedulePreview>(`/api/v1/projects/${projectId}/planning/schedule-preview`, {
    method: "POST",
    body,
    timeoutMs: 30_000,
  });
}
