import { request } from "@/lib/http";
import type { PlanningContext, Participant, PlanVersion } from "@/types/planning";
const base = (id: number) => `/api/v1/projects/${id}/planning`;
export const fetchPlanning = (id: number) => request<PlanningContext>(base(id), { cache: "no-store" });
export const savePlanning = (id: number, path: string, body: unknown, method = "POST") =>
  request<unknown>(`${base(id)}/${path}`, { method, body });
export const fetchParticipants = (id: number, taskId: number) =>
  request<Participant[]>(`${base(id)}/tasks/${taskId}/participants`, { cache: "no-store" });
export const fetchPlanVersion = (id: number, versionId: number) =>
  request<PlanVersion>(`${base(id)}/versions/${versionId}`, { cache: "no-store" });
