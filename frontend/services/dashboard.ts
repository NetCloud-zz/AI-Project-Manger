import { request } from "@/lib/http";
import type { DashboardData } from "@/types/dashboard";

export async function fetchDashboard(): Promise<DashboardData> {
  return request<DashboardData>("/api/v1/dashboard", { cache: "no-store" });
}
