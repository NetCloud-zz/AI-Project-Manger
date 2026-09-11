"""Management Agent — natural-language project status queries via tool calling."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session

from app.agents.context_builder import with_current_time_context
from app.agents.management_tools import (
    MANAGEMENT_TOOLS,
    ManagementToolExecutor,
    extract_project_code,
    format_stub_reply,
    infer_stub_tools,
)
from app.agents.stream_events import AgentStreamEvent, friendly_tool_name
from app.agents.tool_result import parse_tool_result_json, unwrap_tool_data
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway, create_llm_gateway
from app.llm.schemas import ChatMessage, ToolCall
from app.models.user import User
from app.prompts import load_prompt
from app.schemas.agent import AgentChatResponse
from app.services.agent_entities import (
    authorization_source,
    requires_fresh_facts,
    should_use_command_plan,
)
from app.services.management_query import ManagementQueryService

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 20  # kept for older imports; prefer the split caps below
MAX_AGENT_REASONING_ROUNDS = 20
MAX_TOOL_CORRECTION_ROUNDS = 10
SYSTEM_PROMPT = load_prompt("management_agent")
_WRITE_CORRECTION_TOOLS = frozenset(
    {
        "batch_create_tasks",
        "batch_update_tasks",
        "draft_project_plan",
        "update_project_plan_draft",
        "apply_project_plan",
        "create_task",
        "create_project",
        "update_task",
        "update_project",
        "propose_change",
        "execute_change_plan",
    }
)


def _prior_user_texts(context_messages: list[ChatMessage] | None) -> list[str]:
    if not context_messages:
        return []
    return [
        item.content
        for item in context_messages
        if item.role == "user" and isinstance(item.content, str) and item.content.strip()
    ]


def _write_auth_source(
    message: str,
    *,
    context_messages: list[ChatMessage] | None,
    agent_request_id: int | None,
) -> str | None:
    if agent_request_id is None:
        return None
    return authorization_source(message, _prior_user_texts(context_messages))


class CorrectionTracker:
    """Count parameter retries for one write operation. Reads do not consume this budget."""

    def __init__(self, limit: int = MAX_TOOL_CORRECTION_ROUNDS) -> None:
        self.limit = limit
        self.counts: dict[str, int] = {}
        self.last_key: str | None = None

    def record(self, tool: str, *, ok: bool, operation_id: str | None) -> bool:
        if tool not in _WRITE_CORRECTION_TOOLS:
            return False
        key = operation_id or tool
        self.last_key = key
        if ok:
            self.counts.pop(key, None)
            return False
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key] >= self.limit

    def diagnosis(self) -> str:
        key = self.last_key or "operation"
        return (
            f"同一操作 {key} 的参数纠错已达 {self.limit} 次，已停止自动重试。"
            "请根据失败 item 的 error_code 补充信息后再发新请求。"
        )


def _reasoning_rounds(settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    return int(getattr(cfg, "AGENT_REASONING_ROUNDS", MAX_AGENT_REASONING_ROUNDS) or MAX_AGENT_REASONING_ROUNDS)


def _correction_rounds(settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    return int(
        getattr(cfg, "AGENT_TOOL_CORRECTION_ROUNDS", MAX_TOOL_CORRECTION_ROUNDS)
        or MAX_TOOL_CORRECTION_ROUNDS
    )


def _budget_exhausted_message(execution_log: list[dict]) -> str:
    """Persist a readable completed/pending-style checklist when tool rounds are exhausted."""
    if not execution_log:
        return (
            "查询步骤过多，本轮尚未执行任何工具。请拆成更具体的问题，或缩小范围后重试。"
        )
    lines = [
        "查询步骤已达上限，以下为本轮已执行工具回执（未完成项需在新请求中继续）：",
    ]
    for index, record in enumerate(execution_log, start=1):
        name = record.get("name") or record.get("tool") or "unknown"
        ok = record.get("success")
        status = "成功" if ok else "失败"
        detail = ""
        if record.get("error_code"):
            detail = f"（{record.get('error_code')}）"
        lines.append(f"{index}. {name} · {status}{detail}")
    lines.append("请基于以上已完成结果继续，或发起新请求补齐未完成查询。")
    return "\n".join(lines)


def runtime_system_prompt(settings: Settings | None = None) -> str:
    """Static management rules plus Asia/Shanghai clock for this request."""
    cfg = settings or get_settings()
    return with_current_time_context(
        SYSTEM_PROMPT
        + "\n查询最近进展、项目是否顺利、最需要关注什么，必须调用 get_project_progress_overview 获取当前事实；"
        "明确报告窗口、覆盖范围及未评估的维度。不得仅凭上一轮回答文本下结论。"
        "\n统计口径：完成率须说明分母（任务数或加权）；无权重时只报告数量比例，不编造项目百分比。"
        "没有历史进展、依赖或预测数据时分别说明，不补造结论。",
        timezone=getattr(cfg, "SCHEDULER_TIMEZONE", "Asia/Shanghai"),
    )


_PRONOUN_RE = re.compile(r"(它|该项目|这个项目|那个项目|此项目)")
_STUB_CHUNK = 12


class ManagementAgent:
    """Orchestrates LLM tool-calling loop with RBAC-aware tool execution."""

    def __init__(
        self,
        db: Session,
        *,
        gateway: LLMGateway | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._injected_gateway = gateway is not None
        self._gateway = gateway or create_llm_gateway(self._settings)

    async def chat(
        self,
        message: str,
        *,
        actor: User,
        context_messages: list[ChatMessage] | None = None,
        allow_writes: bool = True,
        agent_request_id: int | None = None,
    ) -> AgentChatResponse:
        """Answer ``message`` (non-streaming)."""
        if (
            agent_request_id is not None
            and allow_writes
            and should_use_command_plan(
                authorization_source(message, _prior_user_texts(context_messages))
            )
            and self._gateway.configured
        ):
            from app.agents.command_agent import command_stream

            reply, cards = [], []
            async for event in command_stream(
                self._db,
                self._gateway,
                self._settings,
                message,
                actor,
                agent_request_id,
                context_messages,
            ):
                if event.event == "delta":
                    reply.append(event.data["content"])
                elif event.event == "card":
                    cards = [event.data]
            return AgentChatResponse(reply="".join(reply), cards=cards, llm_used=True)
        if not self._gateway.configured:
            return self._stub_chat(
                message,
                actor=actor,
                context_messages=context_messages,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            )
        if self._should_use_agentscope():
            reply, cards = [], []
            tools_used: list[str] = []
            tool_results: list[dict] = []
            async for event in self._agentscope_stream(
                message,
                actor=actor,
                context_messages=context_messages,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            ):
                if event.event == "delta":
                    reply.append(str(event.data.get("content") or ""))
                elif event.event == "card":
                    cards.append(event.data)
                elif event.event == "tool_start":
                    name = str(event.data.get("tool") or "")
                    if name:
                        tools_used.append(name)
                elif event.event == "tool_end":
                    tool_results.append(dict(event.data))
            return AgentChatResponse(
                reply="".join(reply) or "没有查到相关数据。",
                tools_used=list(dict.fromkeys(tools_used)),
                tool_results=tool_results,
                cards=cards,
                llm_used=True,
            )

        executor = ManagementToolExecutor(
            self._db,
            actor,
            allow_writes=allow_writes,
            agent_request_id=agent_request_id,
            source_message=_write_auth_source(
                message, context_messages=context_messages, agent_request_id=agent_request_id
            ),
        )
        messages = context_messages or [
            ChatMessage(role="system", content=runtime_system_prompt(self._settings)),
            ChatMessage(role="user", content=message),
        ]
        messages = self._prime_fresh_facts(messages, executor, message, actor)

        try:
            tracker = CorrectionTracker(limit=_correction_rounds(self._settings))
            for _round in range(_reasoning_rounds(self._settings)):
                response = await self._gateway.chat_with_tools(
                    messages=messages,
                    tools=MANAGEMENT_TOOLS,
                    model=self._settings.LLM_MODEL_REASONING,
                )
                if not response.tool_calls:
                    reply = response.content.strip() or "没有查到相关数据。"
                    return AgentChatResponse(
                        reply=reply,
                        tools_used=list(dict.fromkeys(executor.tools_used)),
                        tool_results=list(executor.execution_log),
                        cards=list(executor.cards),
                        llm_used=True,
                    )

                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content or "",
                        tool_calls=response.tool_calls,
                    )
                )
                for call in response.tool_calls:
                    tool_result = executor.execute(call.name, call.arguments, tool_call_id=call.id)
                    parsed = parse_tool_result_json(tool_result)
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=tool_result,
                            tool_call_id=call.id,
                        )
                    )
                    if tracker.record(
                        call.name, ok=parsed.ok, operation_id=parsed.operation_id
                    ):
                        return AgentChatResponse(
                            reply=tracker.diagnosis(),
                            tools_used=list(dict.fromkeys(executor.tools_used)),
                            tool_results=list(executor.execution_log),
                            cards=list(executor.cards),
                            llm_used=True,
                        )

            logger.warning("agent.management.max_tool_rounds", rounds=_reasoning_rounds(self._settings))
            return AgentChatResponse(
                reply=_budget_exhausted_message(executor.execution_log),
                tools_used=list(dict.fromkeys(executor.tools_used)),
                tool_results=list(executor.execution_log),
                cards=list(executor.cards),
                llm_used=True,
            )
        except LLMError as exc:
            logger.warning("agent.management.llm_error", error=str(exc))
            stub = self._stub_chat(
                message,
                actor=actor,
                context_messages=context_messages,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            )
            stub_prefix = "（AI 服务暂时不可用，以下为工具查询结果）\n\n"
            unconfigured_prefix = "（LLM 未配置，以下为工具查询结果）\n\n"
            stub.reply = stub_prefix + stub.reply.replace(unconfigured_prefix, "")
            return stub

    async def chat_stream(
        self,
        message: str,
        *,
        actor: User,
        context_messages: list[ChatMessage] | None = None,
        allow_writes: bool = True,
        agent_request_id: int | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Stream answer events (delta / tool_*). Caller owns message_start/done."""
        if (
            agent_request_id is not None
            and allow_writes
            and should_use_command_plan(
                authorization_source(message, _prior_user_texts(context_messages))
            )
            and self._gateway.configured
        ):
            from app.agents.command_agent import command_stream

            async for event in command_stream(
                self._db,
                self._gateway,
                self._settings,
                message,
                actor,
                agent_request_id,
                context_messages,
            ):
                yield event
            return
        if not self._gateway.configured:
            async for event in self._stub_chat_stream(
                message,
                actor=actor,
                context_messages=context_messages,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            ):
                yield event
            return
        if self._should_use_agentscope():
            async for event in self._agentscope_stream(
                message,
                actor=actor,
                context_messages=context_messages,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            ):
                yield event
            return

        executor = ManagementToolExecutor(
            self._db,
            actor,
            allow_writes=allow_writes,
            agent_request_id=agent_request_id,
            source_message=_write_auth_source(
                message, context_messages=context_messages, agent_request_id=agent_request_id
            ),
        )
        emitted_cards = 0
        messages = context_messages or [
            ChatMessage(role="system", content=runtime_system_prompt(self._settings)),
            ChatMessage(role="user", content=message),
        ]
        messages = self._prime_fresh_facts(messages, executor, message, actor)

        try:
            tracker = CorrectionTracker(limit=_correction_rounds(self._settings))
            for _round in range(_reasoning_rounds(self._settings)):
                content_parts: list[str] = []
                tool_calls: list[ToolCall] = []

                async for delta in self._gateway.chat_with_tools_stream(
                    messages=messages,
                    tools=MANAGEMENT_TOOLS,
                    model=self._settings.LLM_MODEL_REASONING,
                ):
                    if delta.content:
                        content_parts.append(delta.content)
                        # Live token push; tool rounds almost never mix text + tools.
                        yield AgentStreamEvent(event="delta", data={"content": delta.content})
                    if delta.tool_calls:
                        tool_calls = list(delta.tool_calls)

                full_content = "".join(content_parts)
                if tool_calls:
                    messages.append(
                        ChatMessage(
                            role="assistant",
                            content=full_content,
                            tool_calls=tool_calls,
                        )
                    )
                    for call in tool_calls:
                        if agent_request_id is not None:
                            from app.models.agent_request import AgentRequest

                            req = self._db.get(AgentRequest, agent_request_id)
                            if req is not None and req.cancel_requested:
                                yield AgentStreamEvent(
                                    event="delta",
                                    data={"content": "（已停止）"},
                                )
                                return
                        yield AgentStreamEvent(
                            event="tool_start",
                            data={
                                "tool": call.name,
                                "label": friendly_tool_name(call.name),
                                "tool_call_id": call.id,
                            },
                        )
                        envelope = executor.execute_result(
                            call.name, call.arguments, tool_call_id=call.id
                        )
                        tool_result = envelope.to_json()
                        yield AgentStreamEvent(
                            event="tool_end",
                            data=envelope.sse_payload(
                                tool=call.name,
                                label=friendly_tool_name(call.name),
                            ),
                        )
                        for card in executor.cards[emitted_cards:]:
                            yield AgentStreamEvent(event="card", data=card)
                        emitted_cards = len(executor.cards)
                        messages.append(
                            ChatMessage(
                                role="tool",
                                content=tool_result,
                                tool_call_id=call.id,
                            )
                        )
                        if tracker.record(
                            call.name, ok=envelope.ok, operation_id=envelope.operation_id
                        ):
                            yield AgentStreamEvent(
                                event="delta", data={"content": tracker.diagnosis()}
                            )
                            return
                    continue

                if not full_content.strip():
                    yield AgentStreamEvent(event="delta", data={"content": "没有查到相关数据。"})
                return

            logger.warning(
                "agent.management.max_tool_rounds", rounds=_reasoning_rounds(self._settings)
            )
            yield AgentStreamEvent(
                event="delta",
                data={"content": _budget_exhausted_message(executor.execution_log)},
            )
        except LLMError as exc:
            logger.warning("agent.management.llm_error", error=str(exc))
            stub_prefix = "（AI 服务暂时不可用，以下为工具查询结果）\n\n"
            async for event in self._stub_chat_stream(
                message,
                actor=actor,
                context_messages=context_messages,
                reply_prefix=stub_prefix,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            ):
                yield event

    def _should_use_agentscope(self) -> bool:
        runtime = getattr(self._settings, "AGENT_RUNTIME", "agentscope")
        if runtime != "agentscope" or self._injected_gateway:
            return False
        from app.agents.agentscope_runtime import is_agentscope_available

        if is_agentscope_available():
            return True
        logger.warning("agent.agentscope.unavailable_fallback_legacy")
        return False

    async def _agentscope_stream(
        self,
        message: str,
        *,
        actor: User,
        context_messages: list[ChatMessage] | None,
        allow_writes: bool,
        agent_request_id: int | None,
    ) -> AsyncIterator[AgentStreamEvent]:
        from app.agents.agentscope_runtime import run_agentscope_chat_stream

        executor = ManagementToolExecutor(
            self._db,
            actor,
            allow_writes=allow_writes,
            agent_request_id=agent_request_id,
            source_message=_write_auth_source(
                message, context_messages=context_messages, agent_request_id=agent_request_id
            ),
        )
        messages = context_messages or [
            ChatMessage(role="system", content=runtime_system_prompt(self._settings)),
            ChatMessage(role="user", content=message),
        ]
        messages = self._prime_fresh_facts(messages, executor, message, actor)
        try:
            async for event in run_agentscope_chat_stream(
                self._db,
                self._settings,
                message,
                actor=actor,
                context_messages=messages,
                executor=executor,
                agent_request_id=agent_request_id,
            ):
                yield event
        except LLMError as exc:
            logger.warning("agent.management.llm_error", error=str(exc), runtime="agentscope")
            stub_prefix = "（AI 服务暂时不可用，以下为工具查询结果）\n\n"
            async for event in self._stub_chat_stream(
                message,
                actor=actor,
                context_messages=context_messages,
                reply_prefix=stub_prefix,
                allow_writes=allow_writes,
                agent_request_id=agent_request_id,
            ):
                yield event

    def _prime_fresh_facts(
        self,
        messages: list[ChatMessage],
        executor: ManagementToolExecutor,
        message: str,
        actor: User,
    ) -> list[ChatMessage]:
        """Force a live overview query for status follow-ups; never reuse prior prose."""
        if not requires_fresh_facts(message):
            return messages
        code = extract_project_code(message)
        if code is None and _PRONOUN_RE.search(message):
            code = _project_code_from_context(messages)
        if not code:
            primed = list(messages)
            primed.append(
                ChatMessage(
                    role="system",
                    content=(
                        "用户在问最近进展/是否顺利/最需要关注。"
                        "必须先确定可见项目（get_project / 澄清），再调用 get_project_progress_overview；"
                        "禁止仅凭历史回答断言事实。"
                    ),
                )
            )
            return primed
        args: dict = {"project_code": code}
        call_id = "prime-overview"
        envelope = executor.execute_result(
            "get_project_progress_overview", args, tool_call_id=call_id
        )
        primed = list(messages)
        primed.append(
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id=call_id, name="get_project_progress_overview", arguments=args)
                ],
            )
        )
        primed.append(
            ChatMessage(role="tool", content=envelope.to_json(), tool_call_id=call_id)
        )
        return primed

    async def _stub_chat_stream(
        self,
        message: str,
        *,
        actor: User,
        context_messages: list[ChatMessage] | None = None,
        reply_prefix: str = "",
        allow_writes: bool = True,
        agent_request_id: int | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        stub = self._stub_chat(
            message,
            actor=actor,
            context_messages=context_messages,
            allow_writes=allow_writes,
            agent_request_id=agent_request_id,
        )
        # Emit tool activity for UX parity with the live path.
        for record in stub.tool_results:
            name = str(record.get("name") or "")
            if not name:
                continue
            yield AgentStreamEvent(
                event="tool_start",
                data={"tool": name, "label": friendly_tool_name(name)},
            )
            yield AgentStreamEvent(
                event="tool_end",
                data={
                    "tool": name,
                    "label": friendly_tool_name(name),
                    "success": bool(record.get("success", True)),
                    "error_code": record.get("error_code"),
                    "error_message": record.get("error_message"),
                    "retryable": record.get("retryable"),
                },
            )
        reply = reply_prefix + stub.reply
        unconfigured_prefix = "（LLM 未配置，以下为工具查询结果）\n\n"
        if reply_prefix and unconfigured_prefix in reply:
            reply = reply.replace(unconfigured_prefix, "")
        for piece in _chunk_text(reply, size=_STUB_CHUNK):
            yield AgentStreamEvent(event="delta", data={"content": piece})
            await asyncio.sleep(0)

    def _stub_chat(
        self,
        message: str,
        *,
        actor: User,
        context_messages: list[ChatMessage] | None = None,
        allow_writes: bool = True,
        agent_request_id: int | None = None,
    ) -> AgentChatResponse:
        executor = ManagementToolExecutor(
            self._db,
            actor,
            allow_writes=allow_writes,
            agent_request_id=agent_request_id,
        )
        parsed_results: list[tuple[str, object]] = []

        resolved = message
        code = extract_project_code(message)
        if code is None and context_messages and _PRONOUN_RE.search(message):
            code = _project_code_from_context(context_messages)
            if code:
                resolved = f"{message}\n（上下文项目：{code}）"

        if requires_fresh_facts(message) or (
            code
            and any(
                keyword in message for keyword in ("怎么样", "状态", "进展", "风险", "延期", "顺利")
            )
        ):
            args: dict = {}
            if code:
                args["project_code"] = code
            planned = [("get_project_progress_overview", args)]
            parsed_results = self._run_planned_tools(executor, planned)
        elif any(
            keyword in message
            for keyword in ("我的任务", "我负责", "我今天", "我有哪些任务", "我有什么任务")
        ):
            preset = None
            if "今天" in message:
                preset = "today"
            elif "本周" in message:
                preset = "this_week"
            elif "下周" in message:
                preset = "next_week"
            args = {}
            if preset:
                args["date_preset"] = preset
            planned = [("list_my_tasks", args)]
            parsed_results = self._run_planned_tools(executor, planned)
        elif any(
            keyword in message
            for keyword in ("今天", "本周", "下周", "未来7天", "未来七天", "截止")
        ):
            if "下周" in message:
                preset = "next_week"
            elif "本周" in message:
                preset = "this_week"
            elif "未来7" in message or "未来七" in message:
                preset = "next_7_days"
            else:
                preset = "today"
            planned = [("search_tasks", {"date_preset": preset})]
            parsed_results = self._run_planned_tools(executor, planned)
        elif any(
            keyword in message
            for keyword in ("风险记录", "有哪些风险", "项目风险", "所有风险", "全局风险")
        ):
            planned = [("list_risk_events", {})]
            parsed_results = self._run_planned_tools(executor, planned)
        elif "负责哪些任务" in message or "负责的任务" in message:
            from app.agents.management_tools import _extract_owner_name

            owner_name = _extract_owner_name(message)
            if owner_name:
                query = ManagementQueryService(self._db)
                tasks = query.list_tasks_by_owner_name(actor, owner_name)
                executor.tools_used.append("list_project_tasks")
                executor.execution_log.append({"name": "list_project_tasks", "success": True})
                parsed_results = [("list_project_tasks", tasks)]
            else:
                planned = infer_stub_tools(resolved)
                parsed_results = self._run_planned_tools(executor, planned)
        else:
            planned = infer_stub_tools(resolved)
            if (
                code
                and planned
                and planned[0][0]
                in (
                    "get_management_attention_items",
                    "list_projects",
                )
            ):
                planned = [("get_project", {"project_code": code})]
            parsed_results = self._run_planned_tools(executor, planned)

        reply = format_stub_reply(resolved, parsed_results)
        return AgentChatResponse(
            reply=reply,
            tools_used=list(dict.fromkeys(executor.tools_used)),
            tool_results=list(executor.execution_log),
            cards=list(executor.cards),
            llm_used=False,
        )

    @staticmethod
    def _run_planned_tools(
        executor: ManagementToolExecutor,
        planned: list[tuple[str, dict[str, object]]],
    ) -> list[tuple[str, object]]:
        parsed: list[tuple[str, object]] = []
        for tool_name, args in planned:
            envelope = executor.execute_result(tool_name, args)
            parsed.append((tool_name, unwrap_tool_data(envelope)))
        return parsed


def _project_code_from_context(messages: list[ChatMessage]) -> str | None:
    for msg in reversed(messages):
        if msg.role not in ("user", "assistant", "system"):
            continue
        code = extract_project_code(msg.content or "")
        if code:
            return code
    return None


def _chunk_text(text: str, *, size: int) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
