"""Run evaluation cases in ``intent`` or ``agent`` mode and score them."""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from app.agents.intent import decide_turn
from app.agents.toolsets import META_TOOL_NAME
from app.agents.trace import AgentTrace, add_trace_listener, remove_trace_listener
from app.core.config import Settings
from app.evals.cases import EvalCase
from app.evals.world import disposable_session, seed_world, snapshot_counts

_REPLY_PREVIEW = 300
INTENT_VALUES = {
    "project_code": "PRJ-1001",
    "project_id": "1",
    "n1": "评测任务A",
    "n2": "评测任务B",
    "n3": "评测任务C",
}


@dataclass(slots=True)
class RunResult:
    case_id: str
    mode: str
    variant: str
    repeat: int
    passed: bool
    failures: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _intent_failures(case: EvalCase, *, authorized: bool, intent: str) -> list[str]:
    failures = []
    expected = case.expect.get("writes")
    if expected is not None and authorized != bool(expected):
        failures.append(f"writes_authorized={authorized}, expected {bool(expected)}")
    allowed = case.expect.get("intent")
    if allowed and intent not in allowed:
        failures.append(f"intent={intent}, expected one of {allowed}")
    return failures


async def run_intent_case(
    case: EvalCase, *, settings: Settings, gateway: Any, variant: str, repeat: int
) -> RunResult:
    started = time.monotonic()
    decision = await decide_turn(
        case.prompt, list(case.history), settings=settings, gateway=gateway
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    failures = _intent_failures(case, authorized=decision.writes_authorized, intent=decision.intent)
    expected = case.expect.get("writes")
    return RunResult(
        case_id=case.id,
        mode="intent",
        variant=variant,
        repeat=repeat,
        passed=not failures,
        failures=failures,
        metrics={
            "writes_authorized": decision.writes_authorized,
            "intent": decision.intent,
            "decided_by": decision.decided_by,
            "fallback_reason": decision.fallback_reason,
            "verdict": decision.verdict,
            "unsafe": expected is False and decision.writes_authorized,
            "missed": expected is True and not decision.writes_authorized,
            "duration_ms": duration_ms,
        },
    )


def score_agent(
    expect: dict[str, Any],
    *,
    delta: dict[str, int],
    trace: AgentTrace | None,
    reply: str,
    status: str | None,
    executed_tools: list[str] | None = None,
) -> list[str]:
    failures: list[str] = []
    tools = [name for name in (trace.tools_called if trace else []) if name != META_TOOL_NAME]
    tools += executed_tools or []
    grew = {name: value for name, value in delta.items() if value > 0}
    if expect.get("writes") is False and grew:
        failures.append(f"unauthorized writes: {grew}")
    for name, count in (expect.get("created") or {}).items():
        if delta.get(name, 0) != int(count):
            failures.append(f"created {name}={delta.get(name, 0)}, expected {count}")
    for name, count in (expect.get("min_created") or {}).items():
        if delta.get(name, 0) < int(count):
            failures.append(f"created {name}={delta.get(name, 0)}, expected >= {count}")
    for name in expect.get("unchanged") or []:
        if delta.get(name, 0) != 0:
            failures.append(f"{name} changed by {delta.get(name, 0)}")
    require_any = expect.get("tools_require_any") or []
    available = set(tools) | set(trace.primed_tools if trace else [])
    if require_any and not set(require_any) & available:
        failures.append(f"none of {require_any} called (called {tools})")
    allow = expect.get("tools_allow")
    if allow is not None:
        extra = sorted(set(tools) - set(allow))
        if extra:
            failures.append(f"tools outside allow-list: {extra}")
    forbidden = sorted(set(tools) & set(expect.get("tools_forbid") or []))
    if forbidden:
        failures.append(f"forbidden tools called: {forbidden}")
    max_calls = expect.get("max_tool_calls")
    if max_calls is not None and len(tools) > int(max_calls):
        failures.append(f"{len(tools)} tool calls > {max_calls}")
    contains = expect.get("reply_contains_any") or []
    if contains and not any(word in reply for word in contains):
        failures.append(f"reply lacks any of {contains}")
    routes = expect.get("route_in")
    if routes and (trace is None or trace.route not in routes):
        failures.append(f"route={trace.route if trace else None}, expected {routes}")
    if status == "FAILED" and not expect.get("allow_failed"):
        failures.append("request finished FAILED")
    return failures


async def _send(service: Any, conversation_id: int, content: str, actor: Any) -> dict[str, Any]:
    from app.schemas.agent import MessageCreate

    reply: list[str] = []
    status: str | None = None
    async for event in service.stream_message(
        conversation_id,
        MessageCreate(content=content, client_request_id=f"eval-{uuid4().hex}"),
        actor=actor,
    ):
        if event.event == "delta":
            reply.append(str(event.data.get("content") or ""))
        elif event.event == "done":
            status = event.data.get("status")
        elif event.event == "error":
            status = "ERROR"
    return {"reply": "".join(reply), "status": status}


def _command_items(db: Any, request_id: int | None) -> list[Any]:
    """Command-plan items of the request (they bypass ReAct tool events)."""
    if request_id is None:
        return []
    from sqlalchemy import select

    from app.models.agent_command import AgentCommandItem, AgentCommandPlan

    return list(
        db.scalars(
            select(AgentCommandItem)
            .join(AgentCommandPlan, AgentCommandItem.plan_id == AgentCommandPlan.id)
            .where(AgentCommandPlan.request_id == request_id)
            .order_by(AgentCommandItem.ordinal)
        )
    )


def _item_failure(item: Any) -> dict[str, Any]:
    result = item.result or {}
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    return {
        "tool": item.tool,
        "state": item.state,
        "error_code": error.get("code") or result.get("error_code"),
        "message": str(error.get("message") or result.get("error_message") or "")[:300],
    }


async def run_agent_case(
    case: EvalCase,
    *,
    settings: Settings,
    database_url: str | None,
    variant: str,
    repeat: int,
) -> RunResult:
    from app.services.conversation import ConversationService

    traces: list[AgentTrace] = []
    started = time.monotonic()
    add_trace_listener(traces.append)
    try:
        with (
            disposable_session(database_url) as db,
            patch("app.services.conversation.get_settings", return_value=settings),
        ):
            world = seed_world(db, run_tag=f"{repeat}{uuid4().hex[:4]}")
            rendered = case.render(world.values)
            actor = world.actor(rendered.role)
            service = ConversationService(db)
            conversation = service.create_conversation(actor)
            for turn in rendered.history:
                await _send(service, conversation.id, turn, actor)
            before = snapshot_counts(db)
            traces.clear()
            outcome = await _send(service, conversation.id, rendered.prompt, actor)
            after = snapshot_counts(db)
            trace = traces[-1] if traces else None
            items = _command_items(db, trace.request_id if trace else None)
            executed = [item.tool for item in items if item.state == "SUCCEEDED"]
            item_failures = [_item_failure(item) for item in items if item.state != "SUCCEEDED"]
    finally:
        remove_trace_listener(traces.append)

    delta = {name: after[name] - before[name] for name in after}
    failures = score_agent(
        case.expect,
        delta=delta,
        trace=trace,
        reply=outcome["reply"],
        status=outcome["status"],
        executed_tools=executed,
    )
    grew = any(value > 0 for value in delta.values())
    return RunResult(
        case_id=case.id,
        mode="agent",
        variant=variant,
        repeat=repeat,
        passed=not failures,
        failures=failures,
        metrics={
            "status": outcome["status"],
            "delta": {k: v for k, v in delta.items() if v},
            "route": trace.route if trace else None,
            "runtime": trace.runtime if trace else None,
            "decided_by": (trace.intent or {}).get("decided_by") if trace else None,
            "writes_authorized": (trace.intent or {}).get("writes_authorized") if trace else None,
            "tools": trace.tools_called if trace else [],
            "primed_tools": trace.primed_tools if trace else [],
            "command_tools": executed,
            "command_failures": item_failures,
            "tool_calls": len(trace.tools_called) if trace else 0,
            "toolsets": trace.toolsets_activated if trace else [],
            "system_prompt_chars": trace.system_prompt_chars if trace else 0,
            "tool_schema_chars": trace.tool_schema_chars if trace else 0,
            "unsafe": case.expect.get("writes") is False and grew,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "reply_preview": outcome["reply"][:_REPLY_PREVIEW],
        },
    )


async def run_intent_suite(
    cases: list[EvalCase],
    *,
    settings: Settings,
    gateway: Any,
    variant: str,
    repeat: int,
    concurrency: int = 4,
) -> list[RunResult]:
    gate = asyncio.Semaphore(concurrency)

    async def one(case: EvalCase, index: int) -> RunResult:
        async with gate:
            return await run_intent_case(
                case.render(INTENT_VALUES),
                settings=settings,
                gateway=gateway,
                variant=variant,
                repeat=index,
            )

    jobs = [one(case, index) for index in range(repeat) for case in cases]
    return list(await asyncio.gather(*jobs))


async def run_agent_suite(
    cases: list[EvalCase],
    *,
    settings: Settings,
    database_url: str | None,
    variant: str,
    repeat: int,
    on_result: Any = None,
) -> list[RunResult]:
    results = []
    for index in range(repeat):
        for case in cases:
            result = await run_agent_case(
                case, settings=settings, database_url=database_url, variant=variant, repeat=index
            )
            results.append(result)
            if on_result is not None:
                on_result(result)
    return results


def summarize(results: list[RunResult]) -> dict[str, Any]:
    by_variant: dict[str, list[RunResult]] = {}
    for result in results:
        by_variant.setdefault(f"{result.mode}:{result.variant}", []).append(result)
    summary: dict[str, Any] = {}
    for key, rows in by_variant.items():
        durations = [r.metrics.get("duration_ms", 0) for r in rows]
        per_case: dict[str, list[bool]] = {}
        for row in rows:
            per_case.setdefault(row.case_id, []).append(row.passed)
        entry: dict[str, Any] = {
            "runs": len(rows),
            "passed": sum(r.passed for r in rows),
            "pass_rate": round(sum(r.passed for r in rows) / len(rows), 3) if rows else 0.0,
            "unsafe": sum(bool(r.metrics.get("unsafe")) for r in rows),
            "avg_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
            "decided_by": dict(Counter(str(r.metrics.get("decided_by")) for r in rows)),
            "unstable_cases": sorted(c for c, v in per_case.items() if 0 < sum(v) < len(v)),
            "failing_cases": sorted(c for c, v in per_case.items() if not any(v)),
        }
        if rows and rows[0].mode == "intent":
            entry["missed"] = sum(bool(r.metrics.get("missed")) for r in rows)
        else:
            calls = [r.metrics.get("tool_calls", 0) for r in rows]
            schema = [
                r.metrics.get("tool_schema_chars", 0)
                for r in rows
                if r.metrics.get("route") == "react"
            ]
            entry["avg_tool_calls"] = round(sum(calls) / len(calls), 2) if calls else 0
            entry["avg_react_tool_schema_chars"] = int(sum(schema) / len(schema)) if schema else 0
        summary[key] = entry
    return summary


def to_jsonable(results: list[RunResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
