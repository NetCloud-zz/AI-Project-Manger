import { request } from "@/lib/http";
import type { DailyProjectSummary } from "@/types/daily_summary";

export async function fetchProjectSummaries(
  projectId: number,
  limit = 30,
): Promise<DailyProjectSummary[]> {
  return request<DailyProjectSummary[]>(
    `/api/v1/projects/${projectId}/summaries?limit=${limit}`,
    { cache: "no-store" },
  );
}

export async function fetchLatestProjectSummary(
  projectId: number,
): Promise<DailyProjectSummary | null> {
  return request<DailyProjectSummary | null>(
    `/api/v1/projects/${projectId}/summaries/latest`,
    { cache: "no-store" },
  );
}

export async function regenerateProjectSummary(
  projectId: number,
): Promise<{ status: string; ai_run_id: number }> {
  return request<{ status: string; ai_run_id: number }>(
    `/api/v1/projects/${projectId}/summaries/regenerate`,
    { method: "POST" },
  );
}
