import { request } from "@/lib/http";
import type { PlanDraft, PlanDraftContent } from "@/types/plan-draft";

const base = "/api/v1/plan-drafts";

export const listPlanDrafts = () => request<PlanDraft[]>(base, { cache: "no-store" });

export const getPlanDraft = (draftId: string) =>
  request<PlanDraft>(`${base}/${draftId}`, { cache: "no-store" });

export const updatePlanDraft = (
  draftId: string,
  body: { expected_revision: number; title: string; content: PlanDraftContent },
) => request<PlanDraft>(`${base}/${draftId}`, { method: "PUT", body });

export const reviewPlanDraft = (draftId: string, expectedRevision: number) =>
  request<PlanDraft>(`${base}/${draftId}/review`, {
    method: "POST",
    body: { expected_revision: expectedRevision },
  });

export const publishPlanDraft = (
  draftId: string,
  body: { expected_revision: number; digest: string; idempotency_key: string },
) => request<PlanDraft>(`${base}/${draftId}/publish`, { method: "POST", body, timeoutMs: 60_000 });

export const discardPlanDraft = (draftId: string, expectedRevision: number) =>
  request<PlanDraft>(`${base}/${draftId}/discard`, {
    method: "POST",
    body: { expected_revision: expectedRevision },
  });
