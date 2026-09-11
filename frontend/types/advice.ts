import type { RiskEvidence } from "@/types/risk";

export type AdviceStatus = "PROPOSED" | "ADOPTED" | "REJECTED" | "SUPERSEDED";
export type AdviceOutcome = "EFFECTIVE" | "PARTIAL" | "INEFFECTIVE";

export interface AdviceOption {
  name: string;
  description?: string;
  /** Estimated working-day effect. Null means the evidence could not support a number. */
  time_impact_days: number | null;
  resource_impact: string | null;
  risks: string[];
}

export interface AdviceContent {
  problem_summary: string;
  possible_causes: string[];
  checks: string[];
  recommended_next_actions: string[];
  suggested_participants: string[];
  escalation_recommended: boolean;
  options: AdviceOption[];
  recommended_option: string | null;
  cited_sources: string[];
  /** Facts the analysis needed and did not have. */
  data_gaps: string[];
}

export interface AdviceCoverage {
  project_tasks_total: number;
  execution_active_tasks: number;
  dependency_neighbours_found: number;
  included: Record<string, number>;
  limits: Record<string, number>;
  excluded: string[];
  generated_at: string;
}

export interface AdviceActionItem {
  id: number;
  title: string;
  status: string;
  owner_id: number | null;
  due_date: string | null;
}

export interface AdviceRecord {
  id: number;
  issue_id: number;
  issue_title: string | null;
  issue_status: string | null;
  project_id: number;
  version: number;
  status: AdviceStatus;
  content: AdviceContent;
  evidence: RiskEvidence[];
  coverage: AdviceCoverage | null;
  context_digest: string | null;
  model: string | null;
  generated_by: number | null;
  generated_at: string | null;
  decided_by: number | null;
  decided_at: string | null;
  decision_note: string | null;
  proposal_id: string | null;
  outcome: AdviceOutcome | null;
  issue_resolved: boolean | null;
  outcome_note: string | null;
  evaluated_at: string | null;
  action_items: AdviceActionItem[];
}

export interface AdviceEffectiveness {
  total: number;
  adopted: number;
  rejected: number;
  pending: number;
  evaluated: number;
  effective: number;
  issues_resolved: number;
}

export interface IssueContextBundle {
  project_id: number;
  project_code: string;
  focus: Record<string, unknown>;
  evidence: RiskEvidence[];
  coverage: AdviceCoverage;
  data_gaps: string[];
}

export const ADVICE_STATUS_LABELS: Record<AdviceStatus, string> = {
  PROPOSED: "待处置",
  ADOPTED: "已采纳",
  REJECTED: "未采纳",
  SUPERSEDED: "已被新版本取代",
};

export const ADVICE_STATUS_COLORS: Record<AdviceStatus, string> = {
  PROPOSED: "blue",
  ADOPTED: "green",
  REJECTED: "default",
  SUPERSEDED: "default",
};

export const ADVICE_OUTCOME_LABELS: Record<AdviceOutcome, string> = {
  EFFECTIVE: "有效",
  PARTIAL: "部分有效",
  INEFFECTIVE: "无效",
};
