import { request } from "@/lib/http";
import type { ChangeProposal } from "@/types/change-proposal";

const base = (projectId: number) => `/api/v1/projects/${projectId}/planning/change-proposals`;
export const listProposals = (projectId: number) => request<ChangeProposal[]>(base(projectId), { cache: "no-store" });
export const getProposal = (projectId: number, id: string) => request<ChangeProposal>(`${base(projectId)}/${id}`, { cache: "no-store" });
export const createProposal = (projectId: number, body: unknown) => request<ChangeProposal>(base(projectId), { method: "POST", body, timeoutMs: 30000 });
export const editProposal = (projectId: number, id: string, body: unknown) => request<ChangeProposal>(`${base(projectId)}/${id}`, { method: "PUT", body });
export const proposalAction = (projectId: number, id: string, action: string, body: unknown) => request<ChangeProposal>(`${base(projectId)}/${id}/${action}`, { method: "POST", body, timeoutMs: 60000 });
