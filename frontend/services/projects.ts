import { request } from "@/lib/http";
import type {
  Project,
  ProjectCreateInput,
  ProjectOwnerBrief,
  ProjectOwnersUpdateInput,
  ProjectScheduleUpdateInput,
  ProjectUpdateInput,
} from "@/types/project";
import type { ProjectForecast } from "@/types/forecast";
import type { Task, TaskCreateInput } from "@/types/task";

export async function fetchProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects", { cache: "no-store" });
}

export async function fetchProject(projectId: number): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}`, { cache: "no-store" });
}

/** Read-only prediction. Requires plan-manager visibility, so callers must tolerate 403. */
export async function fetchProjectForecast(projectId: number): Promise<ProjectForecast> {
  return request<ProjectForecast>(`/api/v1/projects/${projectId}/forecast`, {
    cache: "no-store",
    timeoutMs: 30_000,
  });
}

export async function createProject(body: ProjectCreateInput): Promise<Project> {
  return request<Project>("/api/v1/projects", { method: "POST", body });
}

export async function updateProject(
  projectId: number,
  body: ProjectUpdateInput,
): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}`, { method: "PATCH", body });
}

export async function updateProjectOwners(
  projectId: number,
  body: ProjectOwnersUpdateInput,
): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}/owners`, { method: "PUT", body });
}

export async function updateProjectSchedule(
  projectId: number,
  body: ProjectScheduleUpdateInput,
): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}/schedule`, {
    method: "PATCH",
    body,
  });
}

export async function deleteProject(
  projectId: number,
  body: { reason: string },
): Promise<void> {
  await request<void>(`/api/v1/projects/${projectId}`, {
    method: "DELETE",
    body,
  });
}

export async function fetchAssignableUsers(projectId: number): Promise<ProjectOwnerBrief[]> {
  return request<ProjectOwnerBrief[]>(`/api/v1/projects/${projectId}/assignable-users`, {
    cache: "no-store",
  });
}

export async function fetchProjectTasks(projectId: number): Promise<Task[]> {
  return request<Task[]>(`/api/v1/projects/${projectId}/tasks`, { cache: "no-store" });
}

export async function createProjectTask(
  projectId: number,
  body: TaskCreateInput,
): Promise<Task> {
  return request<Task>(`/api/v1/projects/${projectId}/tasks`, { method: "POST", body });
}
