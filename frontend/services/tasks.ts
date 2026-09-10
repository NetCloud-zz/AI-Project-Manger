import { request } from "@/lib/http";
import type {
  Task,
  TaskBranchActivateInput,
  TaskBranchCreateInput,
  TaskUpdateInput,
} from "@/types/task";

export async function fetchMyTasks(): Promise<Task[]> {
  return request<Task[]>("/api/v1/tasks/my", { cache: "no-store" });
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
