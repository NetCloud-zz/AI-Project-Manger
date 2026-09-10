import { request } from "@/lib/http";
import type { ReadinessResponse } from "@/types/health";

/**
 * Read backend readiness. Returns `null` instead of throwing so the landing page
 * can render an "unreachable" state while the backend is still booting.
 */
export async function fetchReadiness(): Promise<ReadinessResponse | null> {
  try {
    return await request<ReadinessResponse>("/health/ready", { cache: "no-store" });
  } catch {
    return null;
  }
}
