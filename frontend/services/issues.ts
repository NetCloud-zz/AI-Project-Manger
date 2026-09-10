import { request } from "@/lib/http";
import type { Issue, IssueSeverity, IssueStatus } from "@/types/issue";

export type IssueCreateInput = {
  title: string;
  description: string;
  task_id?: number | null;
  severity?: IssueSeverity;
  status?: IssueStatus;
};

export type IssueUpdateInput = {
  title?: string;
  description?: string;
  severity?: IssueSeverity;
  status?: IssueStatus;
  suggested_solution?: string | null;
};

export async function fetchIssues(params?: {
  project_id?: number;
  task_id?: number;
  status?: string;
  open_only?: boolean;
}): Promise<Issue[]> {
  const search = new URLSearchParams();
  if (params?.project_id != null) search.set("project_id", String(params.project_id));
  if (params?.task_id != null) search.set("task_id", String(params.task_id));
  if (params?.status) search.set("status", params.status);
  if (params?.open_only) search.set("open_only", "true");
  const qs = search.toString();
  return request<Issue[]>(`/api/v1/issues${qs ? `?${qs}` : ""}`, { cache: "no-store" });
}

export async function fetchProjectOpenIssues(projectId: number): Promise<Issue[]> {
  return fetchIssues({ project_id: projectId, open_only: true });
}

export async function createProjectIssue(
  projectId: number,
  body: IssueCreateInput,
): Promise<Issue> {
  return request<Issue>(`/api/v1/projects/${projectId}/issues`, { method: "POST", body });
}

export async function updateIssue(issueId: number, body: IssueUpdateInput): Promise<Issue> {
  return request<Issue>(`/api/v1/issues/${issueId}`, { method: "PATCH", body });
}

export async function fetchIssue(issueId: number): Promise<Issue> {
  return request<Issue>(`/api/v1/issues/${issueId}`, { cache: "no-store" });
}

export async function requestIssueAdvice(
  issueId: number,
): Promise<{ status: string; message: string; ai_run_id?: number | null }> {
  return request<{ status: string; message: string; ai_run_id?: number | null }>(
    `/api/v1/issues/${issueId}/advise`,
    {
      method: "POST",
    },
  );
}

export function parseAiSuggestedSolution(raw: string | null): {
  isAi: boolean;
  advice: Record<string, unknown> | null;
} {
  if (!raw) return { isAi: false, advice: null };
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (data.source !== "AI_SUGGESTED") return { isAi: false, advice: null };
    const advice = { ...data };
    delete advice.source;
    delete advice.generated_at;
    return { isAi: true, advice };
  } catch {
    return { isAi: false, advice: null };
  }
}
