export type ConversationStatus = "ACTIVE" | "ARCHIVED";
export type MessageRole = "USER" | "ASSISTANT" | "SYSTEM";
export type MessageStatus =
  | "PENDING"
  | "STREAMING"
  | "COMPLETED"
  | "FAILED"
  | "STOPPED"
  | "INTERRUPTED";

export type AgentStreamEventName =
  | "message_start"
  | "delta"
  | "tool_start"
  | "tool_end"
  | "card"
  | "done"
  | "error";

/** Structured references the assistant attaches so the UI can offer real actions. */
export type AgentCard =
  | CommandPlan
  | { type: "plan_draft"; draft_id: string; title: string; status: string; revision: number; project_id: number | null }
  | { type: "change_proposal"; project_id: number; proposal_id: string; status: string; revision: number; reason: string }
  | { type: "schedule_preview"; project_id: number; feasible: boolean; changed_tasks: number }
  | { type: "notification_status"; proposal_id?: string; project_id?: number; recipient_id?: number }
  | { type: "risk_events"; project_id?: number | null; scope?: string }
  | { type: "advice"; issue_id: number };

export interface CommandPlan {
  type: "execution_plan";
  request_id: number;
  status: string;
  policy: "atomic" | "independent";
  revision: number;
  expected_count: number;
  succeeded: number;
  remaining: number;
  items: Array<{ item_id: string; source_text: string; state: string; depends_on: string[]; result: { error?: { message: string } | null } | null }>;
}

export interface AgentConversation {
  id: number;
  user_id: number;
  title: string;
  status: ConversationStatus;
  project_id: number | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentMessage {
  id: number;
  conversation_id: number;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  tool_calls: Array<{ name: string }> | null;
  tool_results: Array<Record<string, unknown>> | null;
  cards: AgentCard[] | null;
  model: string | null;
  parent_user_message_id?: number | null;
  regenerated_from_id?: number | null;
  answer_version?: number | null;
  selected_answer_id?: number | null;
  association_status?: string;
  created_at: string;
  completed_at: string | null;
}

export type AgentChatRequest = {
  message: string;
  conversation_id?: number | null;
};

export type AgentChatResponse = {
  reply: string;
  tools_used: string[];
  cards: AgentCard[];
  llm_used: boolean;
  conversation_id?: number | null;
  user_message_id?: number | null;
  assistant_message_id?: number | null;
};

export type SendMessageResponse = {
  conversation: AgentConversation;
  user_message: AgentMessage;
  assistant_message: AgentMessage;
  tools_used: string[];
  llm_used: boolean;
};

export type ToolActivity = {
  tool: string;
  label: string;
  status: "running" | "done" | "failed";
};
