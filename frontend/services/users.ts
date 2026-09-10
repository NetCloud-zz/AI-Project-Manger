import { request } from "@/lib/http";
import type { UserProfile } from "@/types/auth";

export type UserRole = UserProfile["role"];
export type UserStatus = UserProfile["status"];
export type ManagedUser = UserProfile;

export type UserCreateInput = {
  name: string;
  username: string;
  password: string;
  email?: string | null;
  mobile?: string | null;
  department?: string | null;
  wechat_user_id?: string | null;
  role?: UserRole;
};

export type UserUpdateInput = {
  name?: string;
  email?: string | null;
  mobile?: string | null;
  department?: string | null;
  wechat_user_id?: string | null;
  role?: UserRole;
  status?: UserStatus;
};

export async function fetchUsers(): Promise<ManagedUser[]> {
  return request<ManagedUser[]>("/api/v1/users", { cache: "no-store" });
}

export type OaSyncResult = {
  created: number;
  updated: number;
  skipped: number;
  total_oa: number;
};

export async function syncUsersFromOa(): Promise<OaSyncResult> {
  return request<OaSyncResult>("/api/v1/users/sync-from-oa", { method: "POST" });
}

export async function createUser(body: UserCreateInput): Promise<ManagedUser> {
  return request<ManagedUser>("/api/v1/users", { method: "POST", body });
}

export async function updateUser(userId: number, body: UserUpdateInput): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}`, { method: "PATCH", body });
}

export async function resetUserPassword(userId: number, password: string): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}/reset-password`, {
    method: "POST",
    body: { password },
  });
}

/** Soft-delete: sets status=INACTIVE. */
export async function deactivateUser(userId: number): Promise<ManagedUser> {
  return request<ManagedUser>(`/api/v1/users/${userId}`, { method: "DELETE" });
}
