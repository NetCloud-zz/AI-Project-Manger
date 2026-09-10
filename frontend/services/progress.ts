import { request } from "@/lib/http";
import type { ProgressSubmitInput, ProgressUpdate, RecentProgressItem } from "@/types/progress";

export function submitProgress(taskId: number, data: ProgressSubmitInput): Promise<ProgressUpdate> {
  return request<ProgressUpdate>(`/api/v1/tasks/${taskId}/progress`, {
    method: "POST",
    body: data,
  });
}

export function fetchTaskProgress(taskId: number): Promise<ProgressUpdate[]> {
  return request<ProgressUpdate[]>(`/api/v1/tasks/${taskId}/progress`);
}

export function fetchProjectRecentProgress(
  projectId: number,
  limit = 50,
): Promise<RecentProgressItem[]> {
  return request<RecentProgressItem[]>(
    `/api/v1/projects/${projectId}/progress/recent?limit=${limit}`,
  );
}
