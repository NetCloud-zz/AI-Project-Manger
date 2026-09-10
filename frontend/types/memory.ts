export type MemoryScope = "USER" | "PROJECT";
export type MemoryType = "PREFERENCE" | "INSTRUCTION" | "PINNED_CONTEXT";

export interface AgentMemory {
  id: number;
  user_id: number;
  scope: MemoryScope;
  memory_type: MemoryType;
  content: string;
  project_id: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type MemoryCreate = {
  content: string;
  scope?: MemoryScope;
  memory_type?: MemoryType;
  project_id?: number | null;
};

export type MemoryUpdate = {
  content?: string;
  memory_type?: MemoryType;
  is_active?: boolean;
};
