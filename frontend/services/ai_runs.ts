import { request } from "@/lib/http";
import type { AIRun, AIRunType } from "@/types/ai_run";

export async function fetchAIRun(runId: number): Promise<AIRun> {
  return request<AIRun>(`/api/v1/ai-runs/${runId}`, { cache: "no-store" });
}

export async function fetchLatestAIRun(params: {
  resourceType: string;
  resourceId: string | number;
  runType?: AIRunType;
}): Promise<AIRun | null> {
  const search = new URLSearchParams({
    resource_type: params.resourceType,
    resource_id: String(params.resourceId),
  });
  if (params.runType) search.set("run_type", params.runType);
  return request<AIRun | null>(`/api/v1/ai-runs/latest/by-resource?${search}`, {
    cache: "no-store",
  });
}
