import { request } from "@/lib/http";
import type {
  Task,
  TaskBranchActivateInput,
  TaskBranchCreateInput,
  TaskUpdateInput,
} from "@/types/task";

export type MyTasksPage = {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
};

export type MyTasksQuery = {
  page?: number;
  pageSize?: number;
  status?: string;
  q?: string;
  sort?: "due" | "name" | "project";
};

export async function fetchMyTasks(params: MyTasksQuery = {}): Promise<MyTasksPage> {
  const query = new URLSearchParams();
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  if (params.sort) query.set("sort", params.sort);
  return request<MyTasksPage>(`/api/v1/tasks/my?${query}`, { cache: "no-store" });
}

export async function fetchTask(taskId: number): Promise<Task> {
  return request<Task>(`/api/v1/tasks/${taskId}`, { cache: "no-store" });
}

export async function updateTask(taskId: number, body: TaskUpdateInput): Promise<Task> {
  return request<Task>(`/api/v1/tasks/${taskId}`, { method: "PATCH", body });
}

export async function deleteTask(
  taskId: number,
  body: { reason: string },
): Promise<void> {
  await request<void>(`/api/v1/tasks/${taskId}`, {
    method: "DELETE",
    body,
  });
}

export async function fetchTaskBranches(taskId: number): Promise<Task[]> {
  return request<Task[]>(`/api/v1/tasks/${taskId}/branches`, { cache: "no-store" });
}

export async function createTaskBranch(
  taskId: number,
  body: TaskBranchCreateInput,
): Promise<Task> {
  return request<Task>(`/api/v1/tasks/${taskId}/branches`, { method: "POST", body });
}

export async function activateTaskBranch(
  taskId: number,
  body: TaskBranchActivateInput,
): Promise<Task> {
  return request<Task>(`/api/v1/tasks/${taskId}/activate-branch`, {
    method: "POST",
    body,
  });
}
