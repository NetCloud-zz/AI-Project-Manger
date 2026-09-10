import { request } from "@/lib/http";
import { apiBaseUrl } from "@/lib/env";
import type { LoginRequest, LoginResponse, UserProfile } from "@/types/auth";

export async function login(body: LoginRequest): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", { method: "POST", body });
}

export function wecomLoginUrl(): string {
  return `${apiBaseUrl()}/api/v1/auth/wecom/login`;
}

export async function fetchMe(): Promise<UserProfile> {
  return request<UserProfile>("/api/v1/me", { cache: "no-store" });
}
