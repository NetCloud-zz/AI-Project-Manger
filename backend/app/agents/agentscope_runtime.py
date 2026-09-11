"""AgentScope 2.x runtime for the Project Assistant ReAct loop."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.agents.agentscope_tools import build_management_toolkit
from app.agents.management_tools import ManagementToolExecutor
from app.agents.stream_events import AgentStreamEvent, friendly_tool_name
from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.schemas import ChatMessage
from app.models.agent_request import AgentRequest
from app.models.user import User

logger = get_logger(__name__)

_CONTINUE_HINT = "请基于以上已查询的事实继续作答，不要重复调用同一查询。"


def is_agentscope_available() -> bool:
    try:
        import agentscope  # noqa: F401
    except ImportError:
        return False
    return True


def _event_type_key(event: Any) -> str:
    raw = getattr(event, "type", None)
    if raw is None:
        return type(event).__name__
    name = getattr(raw, "name", None) or getattr(raw, "value", None)
    if name:
        return str(name)
    text = str(raw)
    return text.rsplit(".", maxsplit=1)[-1]


def _event_delta_text(event: Any) -> str:
    for attr in ("delta", "text", "content"):
        value = getattr(event, attr, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _event_tool_name(event: Any) -> str:
    for attr in ("tool_call_name", "name", "tool", "tool_name"):
        value = getattr(event, attr, None)
        if isinstance(value, str) and value:
            return value
    tool_call = getattr(event, "tool_call", None)
    if tool_call is not None:
        name = getattr(tool_call, "name", None)
        if isinstance(name, str) and name:
            return name
    calls = getattr(event, "tool_calls", None)
    if calls:
        name = getattr(calls[0], "name", None)
        if isinstance(name, str) and name:
            return name
    return ""


def _event_tool_call_id(event: Any) -> str | None:
    for attr in ("tool_call_id", "id"):
        value = getattr(event, attr, None)
        if isinstance(value, str) and value:
            return value
    tool_call = getattr(event, "tool_call", None)
    if tool_call is not None:
        value = getattr(tool_call, "id", None)
        if isinstance(value, str) and value:
            return value
    return None


def _is_cancel_requested(db: Session, request_id: int | None) -> bool:
    if request_id is None:
        return False
    req = db.get(AgentRequest, request_id)
    if req is None:
        return False
    db.refresh(req)
    return bool(req.cancel_requested)


def _split_system_and_rest(
    messages: list[ChatMessage],
) -> tuple[str, list[ChatMessage]]:
    systems = [item.content for item in messages if item.role == "system" and item.content]
    rest = [item for item in messages if item.role != "system"]
    return "\n\n".join(systems), rest


def _to_agentscope_messages(messages: list[ChatMessage]) -> list[Any]:
    from agentscope.message import (
        AssistantMsg,
        TextBlock,
        ToolCallBlock,
        ToolResultBlock,
        UserMsg,
    )

    converted: list[Any] = []
    for item in messages:
        if item.role == "user":
            converted.append(UserMsg(name="user", content=item.content or ""))
            continue
        if item.role == "assistant":
            blocks: list[Any] = []
            if item.content:
                blocks.append(TextBlock(text=item.content))
            for call in item.tool_calls or []:
                blocks.append(
                    ToolCallBlock(
                        id=call.id,
                        name=call.name,
                        input=json.dumps(call.arguments or {}, ensure_ascii=False),
                    )
                )
            converted.append(AssistantMsg(name="assistant", content=blocks or item.content or ""))
            continue
        if item.role == "tool":
            try:
                from agentscope.message import ToolResultState

                result_block = ToolResultBlock(
                    id=item.tool_call_id or "tool",
                    name="tool",
                    output=[TextBlock(text=item.content or "")],
                    state=ToolResultState.SUCCESS,
                )
            except TypeError:
                result_block = ToolResultBlock(
                    id=item.tool_call_id or "tool",
                    output=[TextBlock(text=item.content or "")],
                )
            converted.append(AssistantMsg(name="assistant", content=[result_block]))
    return converted


def _build_openai_model(settings: Settings) -> Any:
    from agentscope.credential import OpenAICredential
    from agentscope.model import OpenAIChatModel

    params = inspect.signature(OpenAICredential).parameters
    cred_kwargs: dict[str, Any] = {"api_key": settings.LLM_API_KEY}
    if "base_url" in params and settings.LLM_BASE_URL:
        cred_kwargs["base_url"] = settings.LLM_BASE_URL
    credential = OpenAICredential(**cred_kwargs)
    if "base_url" not in params and settings.LLM_BASE_URL:
        for attr in ("base_url", "api_base"):
            if hasattr(credential, attr):
                setattr(credential, attr, settings.LLM_BASE_URL)

    model_kwargs: dict[str, Any] = {
        "credential": credential,
        "model": settings.LLM_MODEL_REASONING,
        "stream": True,
        "client_kwargs": {"timeout": settings.LLM_TIMEOUT_SECONDS},
    }
    return OpenAIChatModel(**model_kwargs)


def _build_agent(*, system_prompt: str, settings: Settings, executor: ManagementToolExecutor) -> Any:
    from agentscope.agent import Agent, ReActConfig
    from agentscope.permission import PermissionContext, PermissionMode

    agent_kwargs: dict[str, Any] = {
        "name": "project_assistant",
        "system_prompt": system_prompt,
        "model": _build_openai_model(settings),
        "toolkit": build_management_toolkit(executor),
        "react_config": ReActConfig(max_iters=int(getattr(settings, "AGENT_REASONING_ROUNDS", 20) or 20)),
    }
    try:
        from agentscope.state import AgentState

        agent_kwargs["state"] = AgentState(
            permission_context=PermissionContext(mode=PermissionMode.BYPASS)
        )
    except Exception:  # noqa: BLE001 — AgentState layout varies slightly across 2.x
        logger.info("agent.agentscope.state_skip")
    return Agent(**agent_kwargs)


def _latest_tool_end_event(executor: ManagementToolExecutor) -> AgentStreamEvent | None:
    if not executor.execution_log:
        return None
    record = executor.execution_log[-1]
    name = str(record.get("name") or "")
    if not name:
        return None
    payload: dict[str, Any] = {
        "tool": name,
        "label": friendly_tool_name(name),
        "success": bool(record.get("success", True)),
    }
    for key in ("tool_call_id", "operation_id", "error_code", "error_message", "retryable"):
        if record.get(key) is not None:
            payload[key] = record.get(key)
    return AgentStreamEvent(event="tool_end", data=payload)


def _finished_reason(msg: Any) -> str:
    reason = getattr(msg, "finished_reason", None)
    if reason is None:
        return ""
    return str(getattr(reason, "name", None) or getattr(reason, "value", None) or reason)


async def run_agentscope_chat_stream(
    db: Session,
    settings: Settings,
    message: str,
    *,
    actor: User,
    context_messages: list[ChatMessage],
    executor: ManagementToolExecutor,
    agent_request_id: int | None = None,
    agent_factory: Any | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    """Stream Project Assistant events from an AgentScope Agent."""
    from agentscope.message import Msg, UserMsg

    system_prompt, rest = _split_system_and_rest(context_messages)
    if not system_prompt:
        from app.agents.management_agent import runtime_system_prompt

        system_prompt = runtime_system_prompt(settings)

    factory = agent_factory or _build_agent
    agent = factory(system_prompt=system_prompt, settings=settings, executor=executor)
    if rest and rest[-1].role == "user":
        history, inbound = rest[:-1], UserMsg(name="user", content=rest[-1].content or message)
    else:
        history, inbound = rest, UserMsg(name="user", content=_CONTINUE_HINT)

    if history:
        try:
            observed = agent.observe(_to_agentscope_messages(history))
            if inspect.isawaitable(observed):
                await observed
        except Exception:  # noqa: BLE001
            logger.warning("agent.agentscope.observe_failed", exc_info=True)

    emitted_cards = 0
    saw_text = False
    pending_tool = ""
    pending_tool_call_id: str | None = None
    from app.agents.management_agent import CorrectionTracker, _correction_rounds

    tracker = CorrectionTracker(limit=_correction_rounds(settings))

    try:
        stream = agent.reply_stream(inbound, yield_final_msg=True)
        async for event in stream:
            if _is_cancel_requested(db, agent_request_id):
                yield AgentStreamEvent(event="delta", data={"content": "（已停止）"})
                return
            if isinstance(event, Msg):
                reason = _finished_reason(event)
                if "MAX_ITER" in reason.upper() or "EXCEED" in reason.upper():
                    if not saw_text:
                        from app.agents.management_agent import _budget_exhausted_message

                        yield AgentStreamEvent(
                            event="delta",
                            data={"content": _budget_exhausted_message(executor.execution_log)},
                        )
                        saw_text = True
                continue

            key = _event_type_key(event)
            if key in {"EXCEED_MAX_ITERS", "ExceedMaxItersEvent"}:
                if not saw_text:
                    from app.agents.management_agent import _budget_exhausted_message

                    yield AgentStreamEvent(
                        event="delta",
                        data={"content": _budget_exhausted_message(executor.execution_log)},
                    )
                    saw_text = True
                continue
            if key in {"TEXT_BLOCK_DELTA", "TextBlockDeltaEvent"}:
                text = _event_delta_text(event)
                if text:
                    saw_text = True
                    yield AgentStreamEvent(event="delta", data={"content": text})
                continue
            if key in {"TOOL_CALL_START", "ToolCallStartEvent"}:
                pending_tool = _event_tool_name(event)
                pending_tool_call_id = _event_tool_call_id(event)
                if pending_tool:
                    yield AgentStreamEvent(
                        event="tool_start",
                        data={
                            "tool": pending_tool,
                            "label": friendly_tool_name(pending_tool),
                            "tool_call_id": pending_tool_call_id,
                        },
                    )
                continue
            if key in {"TOOL_RESULT_END", "ToolResultEndEvent"}:
                end_event = _latest_tool_end_event(executor)
                if end_event is None and pending_tool:
                    end_event = AgentStreamEvent(
                        event="tool_end",
                        data={
                            "tool": pending_tool,
                            "label": friendly_tool_name(pending_tool),
                            "success": True,
                            "tool_call_id": pending_tool_call_id,
                        },
                    )
                if end_event is not None:
                    yield end_event
                    if tracker.record(
                        str(end_event.data.get("tool") or pending_tool),
                        ok=bool(end_event.data.get("success", True)),
                        operation_id=(
                            str(end_event.data["operation_id"])
                            if end_event.data.get("operation_id")
                            else None
                        ),
                    ):
                        yield AgentStreamEvent(
                            event="delta", data={"content": tracker.diagnosis()}
                        )
                        return
                for card in executor.cards[emitted_cards:]:
                    yield AgentStreamEvent(event="card", data=card)
                emitted_cards = len(executor.cards)
                pending_tool = ""
                pending_tool_call_id = None
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 — map vendor errors onto the stub path
        logger.warning("agent.agentscope.runtime_error", error=str(exc))
        raise LLMError(str(exc)) from exc

    if not saw_text:
        if _is_cancel_requested(db, agent_request_id):
            yield AgentStreamEvent(event="delta", data={"content": "（已停止）"})
            return
        yield AgentStreamEvent(event="delta", data={"content": "没有查到相关数据。"})
