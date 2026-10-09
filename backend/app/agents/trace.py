"""Per-request assistant trace: route, intent verdict, tool chain and timings.

One ``AgentTrace`` is built per ``ManagementAgent.chat_stream`` call. It observes
the same SSE events the browser receives, so it is runtime-agnostic (AgentScope,
legacy loop, command planner, stub). Payloads never include tool arguments or
results — only names, outcomes and error codes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.stream_events import AgentStreamEvent
from app.core.logging import get_logger

logger = get_logger(__name__)

TraceListener = Callable[["AgentTrace"], None]
_LISTENERS: list[TraceListener] = []


def add_trace_listener(listener: TraceListener) -> None:
    _LISTENERS.append(listener)


def remove_trace_listener(listener: TraceListener) -> None:
    if listener in _LISTENERS:
        _LISTENERS.remove(listener)


@dataclass(slots=True)
class ToolCallTrace:
    tool: str
    ok: bool | None = None
    error_code: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class AgentTrace:
    request_id: int | None
    actor_id: int
    actor_role: str
    route: str = ""
    runtime: str = ""
    intent: dict[str, Any] = field(default_factory=dict)
    toolsets_enabled: bool = False
    toolsets_activated: list[str] = field(default_factory=list)
    system_prompt_chars: int = 0
    tool_schema_chars: int = 0
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    #: Tools run by the backend before the model turn (e.g. fresh progress overview).
    primed_tools: list[str] = field(default_factory=list)
    cards: int = 0
    reply_chars: int = 0
    outcome: str = "completed"
    error: str | None = None
    duration_ms: int = 0
    _started: float = field(default_factory=time.monotonic, repr=False)
    _open: dict[str, tuple[ToolCallTrace, float]] = field(default_factory=dict, repr=False)

    def observe(self, event: AgentStreamEvent) -> None:
        data = event.data or {}
        if event.event == "delta":
            self.reply_chars += len(str(data.get("content") or ""))
        elif event.event == "card":
            self.cards += 1
        elif event.event == "tool_start":
            call = ToolCallTrace(tool=str(data.get("tool") or ""))
            self.tool_calls.append(call)
            key = str(data.get("tool_call_id") or call.tool)
            self._open[key] = (call, time.monotonic())
        elif event.event == "tool_end":
            tool = str(data.get("tool") or "")
            key = str(data.get("tool_call_id") or "")
            if key not in self._open:
                key = next(
                    (k for k, (c, _) in self._open.items() if c.tool == tool),
                    tool,
                )
            opened = self._open.pop(key, None)
            if opened is None:
                call = ToolCallTrace(tool=str(data.get("tool") or ""))
                self.tool_calls.append(call)
            else:
                call, started = opened
                call.duration_ms = int((time.monotonic() - started) * 1000)
            call.ok = bool(data.get("success", True))
            call.error_code = data.get("error_code")
        elif event.event == "error":
            self.outcome = "error"
            self.error = str(data.get("code") or data.get("message") or "error")

    def note_toolset(self, name: str) -> None:
        if name not in self.toolsets_activated:
            self.toolsets_activated.append(name)

    def finish(self, *, outcome: str | None = None, error: str | None = None) -> None:
        if outcome is not None:
            self.outcome = outcome
        if error is not None:
            self.error = error
        self.duration_ms = int((time.monotonic() - self._started) * 1000)

    @property
    def tools_called(self) -> list[str]:
        return [call.tool for call in self.tool_calls if call.tool]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("_started", None)
        payload.pop("_open", None)
        return payload


def emit_trace(trace: AgentTrace, *, log: bool = True) -> None:
    if log:
        failed = [c.tool for c in trace.tool_calls if c.ok is False]
        logger.info(
            "agent.trace",
            request_id=trace.request_id,
            actor_role=trace.actor_role,
            route=trace.route,
            runtime=trace.runtime,
            intent=trace.intent.get("intent"),
            intent_mode=trace.intent.get("mode"),
            writes_authorized=trace.intent.get("writes_authorized"),
            intent_source=trace.intent.get("decided_by"),
            tools=trace.tools_called,
            primed_tools=trace.primed_tools,
            failed_tools=failed,
            toolsets=trace.toolsets_activated,
            system_prompt_chars=trace.system_prompt_chars,
            tool_schema_chars=trace.tool_schema_chars,
            cards=trace.cards,
            reply_chars=trace.reply_chars,
            outcome=trace.outcome,
            error=trace.error,
            duration_ms=trace.duration_ms,
        )
    for listener in list(_LISTENERS):
        try:
            listener(trace)
        except Exception:  # noqa: BLE001 — observers must never break a reply
            logger.warning("agent.trace.listener_failed", exc_info=True)
