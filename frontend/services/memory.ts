import { request } from "@/lib/http";
import type { AgentMemory, MemoryCreate, MemoryUpdate } from "@/types/memory";

export async function fetchMemories(activeOnly = true): Promise<AgentMemory[]> {
  const qs = activeOnly ? "?active_only=true" : "?active_only=false";
  return request<AgentMemory[]>(`/api/v1/agent/memories${qs}`, { cache: "no-store" });
}

export async function createMemory(body: MemoryCreate): Promise<AgentMemory> {
  return request<AgentMemory>("/api/v1/agent/memories", {
    method: "POST",
    body,
  });
}

export async function updateMemory(
  memoryId: number,
  body: MemoryUpdate,
): Promise<AgentMemory> {
  return request<AgentMemory>(`/api/v1/agent/memories/${memoryId}`, {
    method: "PATCH",
    body,
  });
}

export async function deleteMemory(memoryId: number): Promise<void> {
  await request<null>(`/api/v1/agent/memories/${memoryId}`, {
    method: "DELETE",
  });
}
