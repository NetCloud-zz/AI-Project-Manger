import { request } from "@/lib/http";
import type {
  AdviceEffectiveness,
  AdviceRecord,
  IssueContextBundle,
} from "@/types/advice";
import type { RiskEvent, RiskEventStatus, RiskSummary } from "@/types/risk";

interface RiskListResponse {
  items: RiskEvent[];
  summary: RiskSummary;
}

export function listRiskEvents(
  projectId: number,
  status: RiskEventStatus = "OPEN",
): Promise<RiskListResponse> {
  return request<RiskListResponse>(
    `/api/v1/projects/${projectId}/risk-events?status=${status}`,
    { cache: "no-store" },
  );
}

export function refreshRiskEvents(
  projectId: number,
  withForecast = true,
): Promise<RiskListResponse & { counts: Record<string, number> }> {
  return request(`/api/v1/projects/${projectId}/risk-events/refresh`, {
    method: "POST",
    body: { with_forecast: withForecast },
  });
}

export function resolveRiskEvent(eventId: number, resolution: string): Promise<RiskEvent> {
  return request<RiskEvent>(`/api/v1/risk-events/${eventId}/resolve`, {
    method: "POST",
    body: { resolution },
  });
}

export function getIssueContext(issueId: number): Promise<IssueContextBundle> {
  return request<IssueContextBundle>(`/api/v1/issues/${issueId}/context`, {
    cache: "no-store",
  });
}

export function listIssueAdvice(issueId: number): Promise<{ items: AdviceRecord[] }> {
  return request(`/api/v1/issues/${issueId}/advice`, { cache: "no-store" });
}

export function listProjectAdvice(
  projectId: number,
  status?: string,
): Promise<{ items: AdviceRecord[]; effectiveness: AdviceEffectiveness }> {
  const qs = status ? `?status=${status}` : "";
  return request(`/api/v1/projects/${projectId}/advice${qs}`, { cache: "no-store" });
}

export interface AdoptedActionInput {
  title: string;
  description?: string | null;
  owner_id?: number | null;
  task_id?: number | null;
  due_date?: string | null;
  priority?: "LOW" | "MEDIUM" | "HIGH" | "URGENT";
}

export function adoptAdvice(
  adviceId: number,
  body: { note?: string | null; actions: AdoptedActionInput[] },
): Promise<AdviceRecord> {
  return request<AdviceRecord>(`/api/v1/advice/${adviceId}/adopt`, {
    method: "POST",
    body,
  });
}

export function rejectAdvice(adviceId: number, note: string): Promise<AdviceRecord> {
  return request<AdviceRecord>(`/api/v1/advice/${adviceId}/reject`, {
    method: "POST",
    body: { note },
  });
}

export function evaluateAdvice(
  adviceId: number,
  body: { outcome: string; issue_resolved: boolean; note?: string | null },
): Promise<AdviceRecord> {
  return request<AdviceRecord>(`/api/v1/advice/${adviceId}/evaluate`, {
    method: "POST",
    body,
  });
}
