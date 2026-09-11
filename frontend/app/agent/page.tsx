"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { App, Button, Drawer, Input, Spin } from "antd";
import {
  BookOutlined,
  CopyOutlined,
  MenuOutlined,
  ReloadOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from "@ant-design/icons";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { AgentCards } from "@/components/agent/AgentCards";
import { ConversationSidebar } from "@/components/agent/ConversationSidebar";
import { MarkdownRenderer } from "@/components/agent/MarkdownRenderer";
import { MemoryPanel } from "@/components/agent/MemoryPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  createConversation,
  fetchActiveGeneration,
  fetchAgentRequest,
  fetchConversation,
  fetchConversationMessages,
  fetchConversations,
  friendlyToolName,
  regenerateConversationMessage,
  selectAnswerVersion,
  stopAgentRequest,
  streamConversationMessage,
  updateConversation,
} from "@/services/agent";
import { ApiError } from "@/lib/http";
import type { AgentCard, AgentConversation, AgentMessage, ToolActivity } from "@/types/agent";

const AGENT_MESSAGE_MAX_CHARS = 2_000_000;

function answerVersionsFor(
  messages: AgentMessage[],
  userMessageId: number,
): AgentMessage[] {
  return messages
    .filter(
      (item) =>
        item.role === "ASSISTANT" && item.parent_user_message_id === userMessageId,
    )
    .sort((a, b) => (a.answer_version ?? 0) - (b.answer_version ?? 0));
}

/** Timeline for display: hide non-selected answer versions (F08). */
function visibleTimeline(messages: AgentMessage[]): AgentMessage[] {
  const latestByParent = new Map<number, AgentMessage>();
  for (const item of messages) {
    if (item.role !== "ASSISTANT" || item.parent_user_message_id == null) continue;
    const prev = latestByParent.get(item.parent_user_message_id);
    if (!prev || (item.answer_version ?? 0) >= (prev.answer_version ?? 0)) {
      latestByParent.set(item.parent_user_message_id, item);
    }
  }
  const selectedByUser = new Map<number, number>();
  for (const item of messages) {
    if (item.role === "USER" && item.selected_answer_id != null) {
      selectedByUser.set(item.id, item.selected_answer_id);
    }
  }
  return messages.filter((item) => {
    if (item.role !== "ASSISTANT" || item.parent_user_message_id == null) {
      return true;
    }
    const chosen =
      selectedByUser.get(item.parent_user_message_id) ??
      latestByParent.get(item.parent_user_message_id)?.id;
    return chosen == null || item.id === chosen;
  });
}

function sendErrorText(error: unknown): string {
  if (!(error instanceof ApiError)) return "发送失败，请稍后重试";
  const payload = error.payload;
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const tooLong = detail.some(
        (item) =>
          item &&
          typeof item === "object" &&
          "type" in item &&
          (item as { type: unknown }).type === "string_too_long",
      );
      if (tooLong) {
        return `消息过长，请控制在 ${AGENT_MESSAGE_MAX_CHARS.toLocaleString()} 字以内后再发送`;
      }
      return "输入校验失败，请检查消息内容后重试";
    }
  }
  if (error.status === 422) return "输入校验失败，请检查消息内容后重试";
  return "发送失败，请稍后重试";
}

const SUGGESTED_BY_ROLE: Record<string, string[]> = {
  ADMIN: [
    "我今天有哪些任务？",
    "本周有哪些任务截止？",
    "当前可见项目有哪些风险记录？",
    "还有哪些行动项没完成？",
  ],
  EXECUTIVE: [
    "当前可见项目有哪些风险记录？",
    "有什么事情需要我处理？",
    "本周有哪些任务截止？",
    "有哪些问题还没有解决？",
  ],
  PROJECT_OWNER: [
    "我的项目有哪些风险记录？",
    "本周我负责哪些任务？",
    "我的项目有哪些未解决问题？",
    "还有哪些行动项没完成？",
  ],
  MEMBER: [
    "我有哪些任务？",
    "我今天该做什么？",
    "本周我负责哪些任务？",
  ],
};

function toolsSummaryLabel(message: AgentMessage): string | null {
  const results = message.tool_results ?? [];
  if (results.length === 0) {
    const names = message.tool_calls?.map((item) => item.name).filter(Boolean) ?? [];
    if (names.length === 0) return null;
    return `已查询 ${names.length} 项 · ${names.map((name) => friendlyToolName(name)).join("、")}`;
  }
  const writeHints = /^(create_|update_|submit_|propose_|activate_|draft_)/;
  const writes = results.filter((item) => writeHints.test(String(item.name ?? "")));
  const queries = results.filter((item) => !writeHints.test(String(item.name ?? "")));
  const parts: string[] = [];
  if (queries.length) {
    const failed = queries.some((item) => item.success === false);
    parts.push(
      failed
        ? `查询回执 ${queries.length} 项（含失败）`
        : `查询回执 ${queries.length} 项`,
    );
  }
  if (writes.length) {
    const failed = writes.some((item) => item.success === false);
    parts.push(
      failed
        ? `执行回执 ${writes.length} 项（含失败）`
        : `执行回执 ${writes.length} 项`,
    );
  }
  const labels = results.map((item) => friendlyToolName(String(item.name ?? ""))).filter(Boolean);
  return `${parts.join(" · ")} · ${labels.join("、")}`;
}

function AgentPageInner() {
  const { message } = App.useApp();
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlConversationId = Number(searchParams.get("conversation") || "") || null;

  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  useEffect(() => {
    function restoreCommand(event: Event) {
      const source = (event as CustomEvent<unknown>).detail;
      if (typeof source !== "string") return;
      if (sending || input.trim()) {
        message.warning("请先处理当前输入或等待生成结束，再补充原指令。");
        return;
      }
      setInput(source);
    }
    window.addEventListener("agent:restore-command", restoreCommand);
    return () => window.removeEventListener("agent:restore-command", restoreCommand);
  }, [input, sending, message]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [stickToBottom, setStickToBottom] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bootstrapped = useRef(false);

  const [sidebarQuery, setSidebarQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const agentRequestIdRef = useRef<number | null>(null);
  const activeIdRef = useRef<number | null>(null);
  const resumePollTokenRef = useRef(0);

  const suggestions =
    SUGGESTED_BY_ROLE[user?.role ?? ""] ?? SUGGESTED_BY_ROLE.MEMBER;

  const workEntries = [
    "我今天有哪些待办？",
    "当前可见项目有哪些风险记录？",
    "帮我记录一下任务进展",
    "本周项目进展汇总",
  ];

  const scrollToBottom = useCallback((force = false) => {
    requestAnimationFrame(() => {
      const el = listRef.current;
      if (!el) return;
      if (!force && !stickToBottom) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  }, [stickToBottom]);

  const onMessagesScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setStickToBottom(distance < 80);
  }, []);

  const setConversationInUrl = useCallback(
    (id: number | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id == null) params.delete("conversation");
      else params.set("conversation", String(id));
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const refreshConversations = useCallback(async () => {
    const payload = await fetchConversations({
      status: showArchived ? "ARCHIVED" : "ACTIVE",
      limit: 50,
      query: sidebarQuery.trim() || undefined,
    });
    setConversations(payload.items);
    return payload.items;
  }, [showArchived, sidebarQuery]);

  const loadMessages = useCallback(
    async (conversationId: number) => {
      setLoadingMessages(true);
      resumePollTokenRef.current += 1;
      const pollToken = resumePollTokenRef.current;
      try {
        let items = await fetchConversationMessages(conversationId);
        setMessages(items);
        setActiveId(conversationId);
        activeIdRef.current = conversationId;
        setConversationInUrl(conversationId);
        setStickToBottom(true);
        scrollToBottom(true);
        setLoadingMessages(false);

        // Re-enter after leaving mid-stream: restore stop UI / reclaim orphans.
        try {
          const generation = await fetchActiveGeneration(conversationId);
          if (pollToken !== resumePollTokenRef.current) return;
          if (!generation.active || generation.request == null) {
            // Reclaim may have finalized STREAMING — refresh once.
            if (items.some((m) => m.status === "STREAMING")) {
              items = await fetchConversationMessages(conversationId);
              if (pollToken !== resumePollTokenRef.current) return;
              setMessages(items);
            }
            agentRequestIdRef.current = null;
            setSending(false);
            return;
          }
          agentRequestIdRef.current = generation.request.id;
          setSending(true);
          if (generation.request.assistant_content != null) {
            const aid = generation.request.assistant_message_id;
            const content = generation.request.assistant_content;
            const aStatus = generation.request.assistant_status;
            if (aid != null) {
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === aid
                    ? {
                        ...item,
                        content: content ?? item.content,
                        status: (aStatus as AgentMessage["status"]) ?? item.status,
                      }
                    : item,
                ),
              );
            }
          }
          const terminal = new Set([
            "COMPLETED",
            "FAILED",
            "STOPPED",
            "INTERRUPTED",
          ]);
          while (pollToken === resumePollTokenRef.current) {
            await new Promise((r) => setTimeout(r, 1200));
            if (pollToken !== resumePollTokenRef.current) return;
            const status = await fetchAgentRequest(
              conversationId,
              generation.request.id,
            );
            if (status.assistant_content != null && generation.request.assistant_message_id) {
              const aid = generation.request.assistant_message_id;
              setMessages((prev) =>
                prev.map((item) =>
                  item.id === aid
                    ? {
                        ...item,
                        content: status.assistant_content ?? item.content,
                        status:
                          (status.assistant_status as AgentMessage["status"]) ??
                          item.status,
                      }
                    : item,
                ),
              );
            }
            const assistantDone =
              status.assistant_status != null &&
              status.assistant_status !== "STREAMING";
            if (terminal.has(status.status) || assistantDone) break;
          }
          if (pollToken !== resumePollTokenRef.current) return;
          items = await fetchConversationMessages(conversationId);
          setMessages(items);
          agentRequestIdRef.current = null;
          setSending(false);
        } catch {
          /* active-generation optional for older backends */
        }
      } catch {
        message.error("无法加载对话消息");
        setLoadingMessages(false);
      }
    },
    [message, scrollToBottom, setConversationInUrl],
  );

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    let cancelled = false;
    void (async () => {
      try {
        const items = await refreshConversations();
        if (cancelled) return;
        if (urlConversationId) {
          const inList = items.some((item) => item.id === urlConversationId);
          if (inList) {
            await loadMessages(urlConversationId);
          } else {
            try {
              await fetchConversation(urlConversationId);
              await loadMessages(urlConversationId);
            } catch {
              if (items[0]) await loadMessages(items[0].id);
              else {
                setActiveId(null);
                setMessages([]);
              }
            }
          }
        } else if (items[0]) {
          await loadMessages(items[0].id);
        } else {
          setActiveId(null);
          setMessages([]);
        }
      } catch {
        if (!cancelled) message.error("无法加载对话列表");
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Bootstrap once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!bootstrapped.current || loadingList) return;
    void refreshConversations().catch(() => {
      /* ignore search refresh errors */
    });
  }, [sidebarQuery, showArchived, loadingList, refreshConversations]);

  const ensureConversation = useCallback(async (): Promise<number> => {
    if (activeId != null) return activeId;
    const created = await createConversation();
    setConversations((prev) => [created, ...prev]);
    setActiveId(created.id);
    activeIdRef.current = created.id;
    setConversationInUrl(created.id);
    setMessages([]);
    return created.id;
  }, [activeId, setConversationInUrl]);

  const onCreate = useCallback(async () => {
    try {
      resumePollTokenRef.current += 1;
      abortRef.current?.abort();
      const prevRequestId = agentRequestIdRef.current;
      const prevConversationId = activeIdRef.current;
      if (prevRequestId != null && prevConversationId != null) {
        void stopAgentRequest(prevConversationId, prevRequestId).catch(() => {
          /* best-effort */
        });
      }
      agentRequestIdRef.current = null;
      setSending(false);
      const created = await createConversation();
      setConversations((prev) => [created, ...prev]);
      setActiveId(created.id);
      activeIdRef.current = created.id;
      setMessages([]);
      setToolActivities([]);
      setConversationInUrl(created.id);
      setDrawerOpen(false);
    } catch {
      message.error("创建对话失败");
    }
  }, [message, setConversationInUrl]);

  const onSelect = useCallback(
    async (id: number) => {
      resumePollTokenRef.current += 1;
      const prevRequestId = agentRequestIdRef.current;
      const prevConversationId = activeIdRef.current;
      abortRef.current?.abort();
      abortRef.current = null;
      if (
        prevRequestId != null &&
        prevConversationId != null &&
        prevConversationId !== id
      ) {
        void stopAgentRequest(prevConversationId, prevRequestId).catch(() => {
          /* best-effort */
        });
      }
      agentRequestIdRef.current = null;
      setSending(false);
      setDrawerOpen(false);
      setToolActivities([]);
      await loadMessages(id);
    },
    [loadMessages],
  );

  const onRename = useCallback(
    async (id: number, title: string) => {
      try {
        const updated = await updateConversation(id, { title });
        setConversations((prev) =>
          prev.map((item) => (item.id === id ? updated : item)),
        );
      } catch {
        message.error("重命名失败");
      }
    },
    [message],
  );

  const onArchive = useCallback(
    async (id: number) => {
      try {
        await updateConversation(id, { status: "ARCHIVED" });
        const next = await refreshConversations();
        if (activeId === id) {
          if (next[0]) await loadMessages(next[0].id);
          else {
            setActiveId(null);
            setMessages([]);
            setConversationInUrl(null);
          }
        }
      } catch {
        message.error("归档失败");
      }
    },
    [activeId, loadMessages, message, refreshConversations, setConversationInUrl],
  );

  const onRestore = useCallback(
    async (id: number) => {
      try {
        await updateConversation(id, { status: "ACTIVE" });
        setShowArchived(false);
        const next = await refreshConversations();
        await loadMessages(id);
        void next;
      } catch {
        message.error("恢复失败");
      }
    },
    [loadMessages, message, refreshConversations],
  );

  const stopGeneration = useCallback(() => {
    resumePollTokenRef.current += 1;
    const requestId = agentRequestIdRef.current;
    const conversationId = activeIdRef.current ?? activeId;
    if (requestId != null && conversationId != null) {
      void stopAgentRequest(conversationId, requestId)
        .then(() => {
          if (conversationId != null) {
            return fetchConversationMessages(conversationId).then(setMessages);
          }
        })
        .catch(() => {
          /* best-effort */
        });
    }
    abortRef.current?.abort();
    abortRef.current = null;
    agentRequestIdRef.current = null;
    setSending(false);
    setToolActivities([]);
  }, [activeId]);

  // Leave page / switch away: abort SSE and unlock generation slot.
  useEffect(() => {
    const bestEffortStop = () => {
      resumePollTokenRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      const requestId = agentRequestIdRef.current;
      const conversationId = activeIdRef.current;
      if (requestId != null && conversationId != null) {
        void stopAgentRequest(conversationId, requestId).catch(() => {
          /* best-effort */
        });
      }
      agentRequestIdRef.current = null;
    };
    const onPageHide = () => bestEffortStop();
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      bestEffortStop();
    };
  }, []);

  const hasStreamingMessage = messages.some((item) => item.status === "STREAMING");
  const showStop = sending || hasStreamingMessage;
  const runStream = useCallback(
    async (opts: {
      conversationId: number;
      mode: "send" | "regenerate";
      content?: string;
      assistantMessageId?: number;
      optimisticUser?: AgentMessage;
      clientRequestId?: string;
    }) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setSending(true);
      setToolActivities([]);
      setStickToBottom(true);

      let userMessageId: number | null = opts.optimisticUser?.id ?? null;
      let assistantId: number | null =
        opts.mode === "regenerate" ? null : null;
      const streamingAssistantLocalId = -Date.now() - 1;
      let terminalReceived = false;
      agentRequestIdRef.current = null;

      if (opts.mode === "send" && opts.optimisticUser) {
        setMessages((prev) => [
          ...prev,
          opts.optimisticUser!,
          {
            id: streamingAssistantLocalId,
            conversation_id: opts.conversationId,
            role: "ASSISTANT",
            content: "",
            status: "STREAMING",
            tool_calls: null,
            tool_results: null,
            cards: null,
            model: null,
            created_at: new Date().toISOString(),
            completed_at: null,
          },
        ]);
        scrollToBottom(true);
      } else if (opts.mode === "regenerate" && opts.assistantMessageId != null) {
        setMessages((prev) => {
          const parentId = prev.find(
            (item) => item.id === opts.assistantMessageId,
          )?.parent_user_message_id;
          const next: AgentMessage[] = [
            ...prev.map((item) =>
              parentId != null && item.id === parentId
                ? { ...item, selected_answer_id: streamingAssistantLocalId }
                : item,
            ),
            {
              id: streamingAssistantLocalId,
              conversation_id: opts.conversationId,
              role: "ASSISTANT",
              content: "",
              status: "STREAMING",
              tool_calls: null,
              tool_results: null,
              cards: null,
              model: null,
              parent_user_message_id: parentId ?? null,
              answer_version: null,
              regenerated_from_id: opts.assistantMessageId ?? null,
              created_at: new Date().toISOString(),
              completed_at: null,
            },
          ];
          return next;
        });
      }

      const patchAssistant = (patch: Partial<AgentMessage>) => {
        setMessages((prev) =>
          prev.map((item) => {
            const matchId = assistantId ?? streamingAssistantLocalId;
            if (item.id !== matchId && item.id !== streamingAssistantLocalId) {
              return item;
            }
            return { ...item, ...patch, id: patch.id ?? item.id };
          }),
        );
      };

      try {
        const handlers = {
          signal: controller.signal,
          onEvent: (event: string, data: Record<string, unknown>) => {
            if (event === "message_start") {
              const mid = Number(data.message_id);
              const uid = Number(data.user_message_id);
              const version = Number(data.answer_version);
              const reqId = Number(data.agent_request_id);
              if (Number.isFinite(reqId)) {
                agentRequestIdRef.current = reqId;
              }
              if (opts.mode === "send") {
                setInput("");
              }
              if (Number.isFinite(mid)) {
                assistantId = mid;
                patchAssistant({
                  id: mid,
                  status: "STREAMING",
                  parent_user_message_id: Number.isFinite(uid) ? uid : null,
                  answer_version: Number.isFinite(version) ? version : null,
                  regenerated_from_id: data.regenerated_from
                    ? Number(data.regenerated_from)
                    : null,
                });
              }
              if (Number.isFinite(uid)) {
                userMessageId = uid;
                setMessages((prev) =>
                  prev.map((item) => {
                    if (opts.optimisticUser && item.id === opts.optimisticUser!.id) {
                      return { ...item, id: uid, selected_answer_id: mid };
                    }
                    if (
                      opts.mode === "regenerate" &&
                      item.role === "USER" &&
                      item.id === uid
                    ) {
                      return { ...item, selected_answer_id: mid };
                    }
                    return item;
                  }),
                );
              }
            } else if (event === "delta") {
              const piece = String(data.content ?? "");
              if (!piece) return;
              setMessages((prev) =>
                prev.map((item) => {
                  const matchId = assistantId ?? streamingAssistantLocalId;
                  if (item.id !== matchId && item.id !== streamingAssistantLocalId) {
                    return item;
                  }
                  return {
                    ...item,
                    id: assistantId ?? item.id,
                    content: `${item.content}${piece}`,
                    status: "STREAMING",
                  };
                }),
              );
              scrollToBottom();
            } else if (event === "tool_start") {
              const tool = String(data.tool ?? "");
              const label = String(data.label ?? friendlyToolName(tool));
              setToolActivities((prev) => [
                ...prev.filter((item) => item.tool !== tool || item.status !== "running"),
                { tool, label, status: "running" },
              ]);
              scrollToBottom();
            } else if (event === "tool_end") {
              const tool = String(data.tool ?? "");
              const label = String(data.label ?? friendlyToolName(tool));
              const success = data.success !== false;
              setToolActivities((prev) => {
                const without = prev.filter(
                  (item) => !(item.tool === tool && item.status === "running"),
                );
                return [
                  ...without,
                  {
                    tool,
                    label,
                    status: success ? "done" : "failed",
                  },
                ];
              });
            } else if (event === "card") {
              const card = data as unknown as AgentCard;
              if (!card?.type) return;
              setMessages((prev) =>
                prev.map((item) => {
                  const matchId = assistantId ?? streamingAssistantLocalId;
                  if (item.id !== matchId && item.id !== streamingAssistantLocalId) {
                    return item;
                  }
                  const kept = (item.cards ?? []).filter(
                    (existing) => JSON.stringify(existing) !== JSON.stringify(card),
                  );
                  return { ...item, cards: [...kept, card] };
                }),
              );
              scrollToBottom();
            } else if (event === "done") {
              terminalReceived = true;
              const tools = Array.isArray(data.tools_used)
                ? (data.tools_used as string[])
                : [];
              const toolResults = Array.isArray(data.tool_results)
                ? (data.tool_results as Array<Record<string, unknown>>)
                : [];
              const statusRaw = String(data.status ?? "COMPLETED");
              const status =
                statusRaw === "STOPPED" || statusRaw === "INTERRUPTED" || statusRaw === "FAILED"
                  ? (statusRaw as AgentMessage["status"])
                  : "COMPLETED";
              patchAssistant({
                status,
                completed_at: new Date().toISOString(),
                tool_calls: tools.length ? tools.map((name) => ({ name })) : null,
                tool_results: toolResults.length
                  ? toolResults.map((item) => ({
                      name: String(item.name ?? ""),
                      success: item.success !== false,
                      error_code: item.error_code,
                      error_message: item.error_message,
                    }))
                  : tools.length
                    ? tools.map((name) => ({ name, success: true }))
                    : null,
              });
              setToolActivities([]);
            } else if (event === "error") {
              terminalReceived = true;
              patchAssistant({
                status: "FAILED",
                content:
                  String(data.message ?? "") ||
                  "项目助手暂时无法完成回答，请稍后重试。",
                completed_at: new Date().toISOString(),
              });
              if (opts.mode === "send" && opts.content) {
                setInput(opts.content);
              }
              setToolActivities([]);
              message.error(String(data.message ?? "生成失败"));
            }
          },
        };

        if (opts.mode === "send") {
          await streamConversationMessage(
            opts.conversationId,
            opts.content ?? "",
            handlers,
            { clientRequestId: opts.clientRequestId },
          );
        } else {
          await regenerateConversationMessage(
            opts.conversationId,
            opts.assistantMessageId!,
            handlers,
          );
        }

        if (!terminalReceived && !controller.signal.aborted) {
          const reqId = agentRequestIdRef.current;
          if (reqId != null) {
            try {
              const status = await fetchAgentRequest(opts.conversationId, reqId);
              patchAssistant({
                status:
                  (status.assistant_status as AgentMessage["status"]) ||
                  "INTERRUPTED",
                content: status.assistant_content ?? undefined,
                completed_at: new Date().toISOString(),
              });
            } catch {
              patchAssistant({
                status: "INTERRUPTED",
                completed_at: new Date().toISOString(),
              });
            }
          } else {
            patchAssistant({
              status: "INTERRUPTED",
              completed_at: new Date().toISOString(),
            });
          }
          setToolActivities([]);
        }

        void refreshConversations();
        setActiveId(opts.conversationId);
        setConversationInUrl(opts.conversationId);
        scrollToBottom(true);
      } catch (err) {
        if (controller.signal.aborted) {
          patchAssistant({
            status: "STOPPED",
            completed_at: new Date().toISOString(),
          });
          setToolActivities([]);
          return;
        }
        if (opts.mode === "send" && opts.content) {
          setInput(opts.content);
        }
        message.error("发送失败，请稍后重试");
        try {
          setMessages(await fetchConversationMessages(opts.conversationId));
        } catch {
          /* ignore */
        }
        void err;
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setSending(false);
        setToolActivities([]);
        void userMessageId;
      }
    },
    [message, refreshConversations, scrollToBottom, setConversationInUrl],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      if (trimmed.length > AGENT_MESSAGE_MAX_CHARS) {
        message.error(
          `消息过长（${trimmed.length.toLocaleString()} 字），请控制在 ${AGENT_MESSAGE_MAX_CHARS.toLocaleString()} 字以内`,
        );
        return;
      }
      // Keep draft until message_start confirms server accepted the turn (F05).
      const clientRequestId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      try {
        const conversationId = await ensureConversation();
        const optimisticUser: AgentMessage = {
          id: -Date.now(),
          conversation_id: conversationId,
          role: "USER",
          content: trimmed,
          status: "COMPLETED",
          tool_calls: null,
          tool_results: null,
          cards: null,
          model: null,
          created_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        };
        await runStream({
          conversationId,
          mode: "send",
          content: trimmed,
          optimisticUser,
          clientRequestId,
        });
      } catch (error) {
        setInput(trimmed);
        message.error(sendErrorText(error));
        setSending(false);
      }
    },
    [ensureConversation, message, runStream, sending],
  );

  const onRegenerate = useCallback(
    async (assistantMessage: AgentMessage) => {
      if (sending || activeId == null) return;
      await runStream({
        conversationId: activeId,
        mode: "regenerate",
        assistantMessageId: assistantMessage.id,
      });
    },
    [activeId, runStream, sending],
  );

  const onSelectVersion = useCallback(
    async (userMessageId: number, answerId: number) => {
      if (activeId == null || sending) return;
      try {
        const updated = await selectAnswerVersion(activeId, userMessageId, answerId);
        setMessages((prev) =>
          prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
        );
      } catch (error) {
        message.error(sendErrorText(error));
      }
    },
    [activeId, message, sending],
  );

  const onCopy = useCallback(
    async (content: string) => {
      try {
        await navigator.clipboard.writeText(content);
        message.success("已复制");
      } catch {
        message.error("复制失败");
      }
    },
    [message],
  );

  const sidebar = (
    <ConversationSidebar
      conversations={conversations}
      activeId={activeId}
      searchQuery={sidebarQuery}
      onSearchQuery={setSidebarQuery}
      showArchived={showArchived}
      onShowArchived={setShowArchived}
      onSelect={(id) => void onSelect(id)}
      onCreate={() => void onCreate()}
      onRename={(id, title) => void onRename(id, title)}
      onArchive={(id) => void onArchive(id)}
      onRestore={(id) => void onRestore(id)}
    />
  );

  return (
    <div className="agent-page-wrap">
      <div className="agent-page agent-page--with-sidebar">
        <div className="agent-page__sidebar-desktop">{sidebar}</div>

        <div className="agent-page__main">
          <div className="agent-page__header">
            <Button
              className="agent-page__menu"
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setDrawerOpen(true)}
              aria-label="打开对话列表"
            />
            <PageHeader
              title="项目助手"
              
              action={
                <Button icon={<BookOutlined />} onClick={() => setMemoryOpen(true)}>
                  记忆
                </Button>
              }
            />
          </div>

          {loadingList ? (
            <div className="agent-loading">
              <Spin />
            </div>
          ) : (
            <>
              {messages.length === 0 && !loadingMessages ? (
                <div className="agent-empty">
                  <h2 className="agent-empty__title">项目助手</h2>
                  <p className="agent-empty__desc">
                    我可以帮助你查询项目、任务、风险、问题和行动项。对话会保存在左侧列表中。
                  </p>
                  <div className="agent-suggestions agent-suggestions--wrap">
                    {workEntries.map((question) => (
                      <button
                        key={`work-${question}`}
                        type="button"
                        className="suggestion-chip suggestion-chip--work"
                        onClick={() => void sendMessage(question)}
                      >
                        {question}
                      </button>
                    ))}
                    {suggestions.map((question) => (
                      <button
                        key={question}
                        type="button"
                        className="suggestion-chip"
                        onClick={() => void sendMessage(question)}
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <div
                ref={listRef}
                className="agent-messages"
                onScroll={onMessagesScroll}
              >
                {loadingMessages ? (
                  <div className="agent-loading">
                    <Spin size="small" />
                  </div>
                ) : null}
                {visibleTimeline(messages).map((item) => {
                  const roleClass =
                    item.role === "USER" ? "user" : "assistant";
                  const tools = toolsSummaryLabel(item);
                  const versions =
                    item.role === "ASSISTANT" && item.parent_user_message_id != null
                      ? answerVersionsFor(messages, item.parent_user_message_id)
                      : [];
                  return (
                    <div
                      key={item.id}
                      className={`agent-bubble agent-bubble--${roleClass}${
                        item.status === "FAILED" ? " is-failed" : ""
                      }${item.status === "STREAMING" ? " is-streaming" : ""}${
                        item.status === "STOPPED" || item.status === "INTERRUPTED"
                          ? " is-interrupted"
                          : ""
                      }`}
                    >
                      <div className="meta-line agent-bubble__role">
                        {item.role === "USER" ? (
                          <>
                            <UserOutlined /> 我
                          </>
                        ) : (
                          <>
                            <RobotOutlined /> 助手
                            {item.answer_version != null && versions.length > 1
                              ? ` · 版本 ${item.answer_version}/${versions.length}`
                              : null}
                          </>
                        )}
                      </div>
                      <div className="agent-bubble__content">
                        {item.role === "ASSISTANT" ? (
                          item.content ? (
                            <MarkdownRenderer content={item.content} />
                          ) : item.status === "STREAMING" ? (
                            "…"
                          ) : (
                            ""
                          )
                        ) : (
                          item.content
                        )}
                      </div>
                      {tools ? (
                        <div className="meta-line agent-bubble__tools">{tools}</div>
                      ) : null}
                      {item.role === "ASSISTANT" ? <AgentCards cards={item.cards} /> : null}
                      {item.role === "ASSISTANT" && versions.length > 1 ? (
                        <div className="agent-bubble__versions" role="group" aria-label="回答版本">
                          {versions.map((version) => (
                            <Button
                              key={version.id}
                              type={version.id === item.id ? "primary" : "default"}
                              size="small"
                              disabled={sending || version.status === "STREAMING"}
                              onClick={() => {
                                if (
                                  version.parent_user_message_id != null &&
                                  version.id !== item.id
                                ) {
                                  void onSelectVersion(
                                    version.parent_user_message_id,
                                    version.id,
                                  );
                                }
                              }}
                            >
                              v{version.answer_version ?? "?"}
                            </Button>
                          ))}
                        </div>
                      ) : null}
                      {item.role === "ASSISTANT" &&
                      item.status !== "STREAMING" &&
                      item.content ? (
                        <div className="agent-bubble__actions">
                          <Button
                            type="text"
                            size="small"
                            icon={<CopyOutlined />}
                            onClick={() => void onCopy(item.content)}
                          >
                            复制
                          </Button>
                          <Button
                            type="text"
                            size="small"
                            icon={<ReloadOutlined />}
                            disabled={sending}
                            onClick={() => void onRegenerate(item)}
                          >
                            重新生成
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}

                {toolActivities.length > 0 ? (
                  <div className="agent-tool-activity" aria-live="polite">
                    {toolActivities.map((activity, index) => (
                      <div
                        key={`${activity.tool}-${activity.status}-${index}`}
                        className={`agent-tool-activity__item is-${activity.status}`}
                      >
                        {activity.status === "running"
                          ? `正在${activity.label}…`
                          : activity.status === "failed"
                            ? `${activity.label}失败`
                            : `已完成：${activity.label}`}
                      </div>
                    ))}
                  </div>
                ) : null}

                {!stickToBottom && messages.length > 0 ? (
                  <button
                    type="button"
                    className="agent-scroll-bottom"
                    onClick={() => {
                      setStickToBottom(true);
                      scrollToBottom(true);
                    }}
                  >
                    ↓ 回到底部
                  </button>
                ) : null}
              </div>
            </>
          )}

          <div className="agent-input-bar">
            <div className="agent-input-bar__row">
              <Input.TextArea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="输入问题，例如：PRJ-1001 现在怎么样？"
                autoSize={{ minRows: 1, maxRows: 12 }}
                maxLength={AGENT_MESSAGE_MAX_CHARS}
                onPressEnter={(event) => {
                  if (!event.shiftKey && !(event.nativeEvent as KeyboardEvent).isComposing) {
                    event.preventDefault();
                    void sendMessage(input);
                  }
                }}
                disabled={sending || loadingList}
              />
              {showStop ? (
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={stopGeneration}
                >
                  停止
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  aria-label="发送消息"
                  onClick={() => void sendMessage(input)}
                  disabled={loadingList}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      <Drawer
        title="对话"
        placement="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={280}
        styles={{ body: { padding: 0 } }}
      >
        {sidebar}
      </Drawer>

      <MemoryPanel open={memoryOpen} onClose={() => setMemoryOpen(false)} />
    </div>
  );
}

export default function AgentPage() {
  return (
    <RequireAuth>
      <Suspense
        fallback={
          <div className="agent-page-wrap">
            <div className="agent-loading">
              <Spin />
            </div>
          </div>
        }
      >
        <AgentPageInner />
      </Suspense>
    </RequireAuth>
  );
}
