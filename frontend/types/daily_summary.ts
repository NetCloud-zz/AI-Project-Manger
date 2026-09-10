export interface DailyProjectSummary {
  id: number;
  project_id: number;
  summary_date: string;
  summary: string;
  risk_summary: string;
  next_action: string;
  management_attention: string;
  created_at: string;
}

export interface ParsedAiAdvice {
  problem_summary?: string;
  possible_causes?: string[];
  checks?: string[];
  recommended_next_actions?: string[];
  suggested_participants?: string[];
  escalation_recommended?: boolean;
}
