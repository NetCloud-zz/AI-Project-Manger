import { apiBaseUrl } from "@/lib/env";
import { getStoredToken } from "@/lib/auth-storage";
import { ApiError } from "@/lib/http";
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentConversation,
  AgentMessage,
  AgentStreamEventName,
  ConversationStatus,
  SendMessageResponse,
} from "@/types/agent";
import { request } from "@/lib/http";

const TOOL_LABELS: Record<string, string> = {
  list_projects: "查询项目列表",
  get_project: "查询项目",
  list_project_tasks: "查询任务",
  get_task_progress: "查询任务进度",
  list_delayed_tasks: "检查延期任务",
  list_at_risk_tasks: "查询风险任务",
  get_current_user: "确认当前用户",
  search_tasks: "搜索任务",
  list_my_tasks: "查询我的任务",
  list_open_issues: "查询未解决问题",
  list_action_items: "查询行动项",
  get_management_attention_items: "查询管理关注事项",
  find_users: "查询负责人",
  create_project: "创建项目",
  update_project: "更新项目",
  create_task: "创建任务",
  update_task: "更新任务",
  create_issue: "登记问题",
  update_issue: "更新问题",
  create_action_item: "创建行动项",
  update_action_item: "更新行动项",
  list_task_branches: "查询任务分支",
  create_task_branch: "创建备用分支",
  activate_task_branch: "切换任务分支",
  get_project_context: "读取项目上下文",
  get_dependency_graph: "读取依赖与路线",
  draft_project_plan: "起草立项计划",
  update_project_plan_draft: "更新计划草案",
  review_project_plan_draft: "校验计划草案",
  get_project_plan_draft: "查看计划草案",
  preview_change: "模拟变更影响",
  propose_change: "生成变更方案",
  get_change_proposal: "查看变更方案",
  get_notification_status: "查询通知状态",
  submit_progress: "提交进度汇报",
  list_risk_events: "查询风险记录",
  get_issue_evidence: "收集问题证据",
  get_issue_advice: "查看问题建议",
  request_issue_advice: "生成问题建议",
};

export function friendlyToolName(tool: string): string {
  return TOOL_LABELS[tool] ?? tool;
}

export async function sendAgentMessage(body: AgentChatRequest): Promise<AgentChatResponse> {
  return request<AgentChatResponse>("/api/v1/agent/chat", {
    method: "POST",
    body,
    timeoutMs: 60_000,
  });
}

export async function createConversation(body?: {
  title?: string;
  project_id?: number | null;
}): Promise<AgentConversation> {
  return request<AgentConversation>("/api/v1/agent/conversations", {
    method: "POST",
    body: body ?? {},
  });
}

export async function fetchConversations(params?: {
  status?: ConversationStatus;
  limit?: number;
  cursor?: string;
  query?: string;
}): Promise<{ items: AgentConversation[]; next_cursor: string | null }> {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.limit != null) search.set("limit", String(params.limit));
  if (params?.cursor) search.set("cursor", params.cursor);
  if (params?.query) search.set("query", params.query);
  const qs = search.toString();
  return request<{ items: AgentConversation[]; next_cursor: string | null }>(
    `/api/v1/agent/conversations${qs ? `?${qs}` : ""}`,
    { cache: "no-store" },
  );
}

export async function stopAgentRequest(
  conversationId: number,
  agentRequestId: number,
): Promise<{
  id: number;
  status: string;
  cancel_requested: boolean;
  assistant_status: string | null;
}> {
  return request(
    `/api/v1/agent/conversations/${conversationId}/requests/${agentRequestId}/stop`,
    { method: "POST" },
  );
}

export async function fetchActiveGeneration(
  conversationId: number,
): Promise<{
  active: boolean;
  request: {
    id: number;
    status: string;
    cancel_requested: boolean;
    assistant_message_id: number | null;
    assistant_status: string | null;
    assistant_content: string | null;
  } | null;
}> {
  return request(
    `/api/v1/agent/conversations/${conversationId}/active-generation`,
    { cache: "no-store" },
  );
}

export async function fetchAgentRequest(
  conversationId: number,
  agentRequestId: number,
): Promise<{
  id: number;
  status: string;
  cancel_requested: boolean;
  assistant_status: string | null;
  assistant_content: string | null;
}> {
  return request(
    `/api/v1/agent/conversations/${conversationId}/requests/${agentRequestId}`,
    { cache: "no-store" },
  );
}

export async function fetchConversation(conversationId: number): Promise<AgentConversation> {
  return request<AgentConversation>(`/api/v1/agent/conversations/${conversationId}`, {
    cache: "no-store",
  });
}

export async function updateConversation(
  conversationId: number,
  body: { title?: string; status?: ConversationStatus; project_id?: number | null },
): Promise<AgentConversation> {
  return request<AgentConversation>(`/api/v1/agent/conversations/${conversationId}`, {
    method: "PATCH",
    body,
  });
}

export async function fetchConversationMessages(
  conversationId: number,
): Promise<AgentMessage[]> {
  return request<AgentMessage[]>(
    `/api/v1/agent/conversations/${conversationId}/messages`,
    { cache: "no-store" },
  );
}

export async function selectAnswerVersion(
  conversationId: number,
  userMessageId: number,
  answerId: number,
): Promise<AgentMessage> {
  return request<AgentMessage>(
    `/api/v1/agent/conversations/${conversationId}/messages/${userMessageId}/select-answer`,
    {
      method: "POST",
      body: { answer_id: answerId },
    },
  );
}

export async function sendConversationMessage(
  conversationId: number,
  content: string,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(
    `/api/v1/agent/conversations/${conversationId}/messages`,
    {
      method: "POST",
      body: { content },
      timeoutMs: 60_000,
    },
  );
}

export type StreamHandlers = {
  onEvent: (event: AgentStreamEventName, data: Record<string, unknown>) => void;
  signal?: AbortSignal;
};

async function consumeAgentSse(
  path: string,
  body: unknown,
  handlers: StreamHandlers,
): Promise<void> {
  const url = path.startsWith("http") ? path : `${apiBaseUrl()}${path}`;
  const token = getStoredToken();
  const response = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: handlers.signal,
  });

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(`Request failed: ${response.status} ${url}`, response.status, payload);
  }
  if (!response.body) {
    throw new ApiError("Streaming response has no body", response.status, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = flushSseBuffer(buffer, handlers.onEvent);
  }
  buffer += decoder.decode();
  flushSseBuffer(buffer, handlers.onEvent, true);
}

function flushSseBuffer(
  buffer: string,
  onEvent: StreamHandlers["onEvent"],
  flushAll = false,
): string {
  const parts = buffer.split("\n\n");
  const rest = flushAll ? "" : (parts.pop() ?? "");
  for (const block of parts) {
    if (!block.trim()) continue;
    let eventName: AgentStreamEventName | null = null;
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim() as AgentStreamEventName;
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (!eventName) continue;
    let data: Record<string, unknown> = {};
    const raw = dataLines.join("\n");
    if (raw) {
      try {
        data = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        data = { raw };
      }
    }
    onEvent(eventName, data);
  }
  return rest;
}

export async function streamConversationMessage(
  conversationId: number,
  content: string,
  handlers: StreamHandlers,
  options?: { clientRequestId?: string },
): Promise<void> {
  const body: Record<string, string> = { content };
  if (options?.clientRequestId) {
    body.client_request_id = options.clientRequestId;
  }
  await consumeAgentSse(
    `/api/v1/agent/conversations/${conversationId}/messages/stream`,
    body,
    handlers,
  );
}

export async function regenerateConversationMessage(
  conversationId: number,
  assistantMessageId: number,
  handlers: StreamHandlers,
): Promise<void> {
  await consumeAgentSse(
    `/api/v1/agent/conversations/${conversationId}/messages/${assistantMessageId}/regenerate/stream`,
    undefined,
    handlers,
  );
}
