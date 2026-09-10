import { request } from "@/lib/http";
import type {
  ProjectGanttData,
  TaskLink,
  TaskLinkCreateInput,
  TaskLinkType,
} from "@/types/gantt";

export async function fetchProjectGantt(projectId: number): Promise<ProjectGanttData> {
  return request<ProjectGanttData>(`/api/v1/projects/${projectId}/gantt`, {
    cache: "no-store",
  });
}

export async function createTaskLink(
  projectId: number,
  body: TaskLinkCreateInput,
): Promise<TaskLink> {
  return request<TaskLink>(`/api/v1/projects/${projectId}/task-links`, {
    method: "POST",
    body,
  });
}

export async function updateTaskLink(
  linkId: number,
  linkType: TaskLinkType,
  lagDays?: number,
): Promise<TaskLink> {
  return request<TaskLink>(`/api/v1/task-links/${linkId}`, {
    method: "PATCH",
    body: { link_type: linkType, ...(lagDays === undefined ? {} : { lag_days: lagDays }) },
  });
}

export async function deleteTaskLink(linkId: number): Promise<void> {
  await request<null>(`/api/v1/task-links/${linkId}`, { method: "DELETE" });
}
