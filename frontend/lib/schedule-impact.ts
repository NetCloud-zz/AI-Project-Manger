/**
 * Recognises the backend's refusal to let a direct edit reschedule other tasks.
 *
 * The API answers 409 with the list of tasks that would have moved, so the UI
 * can show exactly what the edit would have done and send the user to the
 * change-proposal flow instead of just saying "failed".
 */

import { ApiError } from "@/lib/http";

export const SCHEDULE_IMPACT_CODE = "SCHEDULE_IMPACT_REQUIRES_PROPOSAL";

export interface ImpactedTask {
  task_id: number;
  task_name: string;
  current_start_date: string | null;
  current_finish_date: string | null;
  predicted_start_date: string | null;
  predicted_finish_date: string | null;
}

export interface ScheduleImpact {
  detail: string;
  action: string;
  impacted: ImpactedTask[];
}

export function scheduleImpactOf(error: unknown): ScheduleImpact | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const payload = error.payload as Partial<ScheduleImpact> & { code?: string };
  if (!payload || payload.code !== SCHEDULE_IMPACT_CODE) return null;
  return {
    detail: payload.detail ?? "这次修改会影响其他任务的日期",
    action: payload.action ?? "这次修改",
    impacted: payload.impacted ?? [],
  };
}
