"""Intent decision, tool groups, trace and eval scoring for the assistant rework."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.agents.intent import IntentVerdict, decide_turn, evidence_in_message, regex_decision
from app.agents.management_agent import ManagementAgent
from app.agents.management_tools import MANAGEMENT_TOOLS
from app.agents.stream_events import AgentStreamEvent
from app.agents.tool_result import ToolErrorCode
from app.agents.toolsets import (
    GROUP_OF_TOOL,
    META_TOOL_NAME,
    TOOLSETS,
    ToolsetState,
    core_tools,
    full_toolset_prompt,
    with_toolset_prompt,
)
from app.agents.trace import AgentTrace
from app.core.config import Settings
from app.core.database import Base
from app.evals.cases import load_cases
from app.evals.runner import score_agent
from app.llm.schemas import ChatMessage, StreamDelta, ToolCall
from app.models.agent_command import AgentCommandPlan
from app.models.user import User, UserRole
from app.services.agent_commands import plan_guard_authorized
from app.services.agent_entities import EntityResolutionError, guard_mutation

BACKEND = Path(__file__).resolve().parents[1]


def hybrid_settings(**overrides) -> Settings:
    return Settings(_env_file=None, AGENT_INTENT_MODE="hybrid", **overrides)


class VerdictGateway:
    configured = True

    def __init__(self, verdict: IntentVerdict | Exception | None = None, delay: float = 0.0):
        self.verdict = verdict
        self.delay = delay
        self.calls = 0

    async def structured_output(self, **kwargs):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return self.verdict


# --- intent -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_regex_mode_never_calls_model():
    gateway = VerdictGateway(IntentVerdict(intent="write", writes_requested=True, confidence=1))
    decision = await decide_turn(
        "补三个任务", [], settings=Settings(_env_file=None), gateway=gateway
    )
    assert gateway.calls == 0
    assert decision.mode == "regex" and decision.guard_authorized is None
    assert decision == regex_decision("补三个任务", [])


@pytest.mark.asyncio
async def test_hybrid_authorizes_trusted_write_verdict():
    verdict = IntentVerdict(
        intent="write", writes_requested=True, confidence=0.9, evidence="补三个任务"
    )
    decision = await decide_turn(
        "在 PRJ-1001 补三个任务", [], settings=hybrid_settings(), gateway=VerdictGateway(verdict)
    )
    assert decision.decided_by == "llm"
    assert decision.writes_authorized and decision.guard_authorized is True
    assert decision.route_command_plan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict",
    [
        IntentVerdict(intent="write", writes_requested=True, confidence=0.5, evidence="补三个任务"),
        IntentVerdict(intent="write", writes_requested=True, confidence=0.95, evidence="删除项目"),
        IntentVerdict(
            intent="write", writes_requested=False, confidence=0.95, evidence="补三个任务"
        ),
    ],
    ids=["low_confidence", "evidence_not_in_message", "not_requested"],
)
async def test_hybrid_rejects_untrusted_verdicts(verdict):
    decision = await decide_turn(
        "在 PRJ-1001 补三个任务", [], settings=hybrid_settings(), gateway=VerdictGateway(verdict)
    )
    assert not decision.writes_authorized
    assert decision.guard_authorized is False


@pytest.mark.asyncio
async def test_hybrid_regex_veto_skips_model_for_discussion():
    gateway = VerdictGateway(IntentVerdict(intent="write", writes_requested=True, confidence=1))
    decision = await decide_turn(
        "只是讨论，不要创建任务", [], settings=hybrid_settings(), gateway=gateway
    )
    assert gateway.calls == 0
    assert decision.decided_by == "regex_veto"
    assert decision.guard_authorized is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gateway,reason",
    [
        (VerdictGateway(RuntimeError("boom")), "RuntimeError"),
        (VerdictGateway(IntentVerdict(intent="other"), delay=1), "TimeoutError"),
        (None, "gateway_unavailable"),
    ],
)
async def test_hybrid_falls_back_to_regex(gateway, reason):
    settings = hybrid_settings(AGENT_INTENT_TIMEOUT_SECONDS=0.05)
    decision = await decide_turn(
        "在 PRJ-1001 创建任务 需求评审", [], settings=settings, gateway=gateway
    )
    assert decision.decided_by == "regex_fallback"
    assert decision.fallback_reason == reason
    assert (
        decision.writes_authorized
        == regex_decision("在 PRJ-1001 创建任务 需求评审", []).writes_authorized
    )


@pytest.mark.asyncio
async def test_confirm_previous_uses_indexed_prior_message():
    prior = ["PRJ-1001 进展怎么样", "在 PRJ-1001 补两个任务：接口自测、文档整理"]
    verdict = IntentVerdict(
        intent="confirm_previous",
        writes_requested=True,
        confidence=0.9,
        evidence="好的",
        confirmed_prior=1,
    )
    decision = await decide_turn(
        "好的", prior, settings=hybrid_settings(), gateway=VerdictGateway(verdict)
    )
    assert decision.intent == "confirmation"
    assert decision.authorization_source == prior[1]

    out_of_range = verdict.model_copy(update={"confirmed_prior": 7})
    decision = await decide_turn(
        "好的", prior, settings=hybrid_settings(), gateway=VerdictGateway(out_of_range)
    )
    assert not decision.writes_authorized


def test_evidence_must_come_from_user_text():
    assert evidence_in_message("行", "行")
    assert evidence_in_message("补 三个", "请补三个任务")
    assert not evidence_in_message("行", "可行性怎么样")
    assert not evidence_in_message("", "好的")


# --- write guard ---------------------------------------------------------------------


def test_guard_mutation_respects_explicit_verdict():
    guard_mutation("补三个任务", "create_task", {}, authorized=True)
    with pytest.raises(EntityResolutionError):
        guard_mutation("在 PRJ-1001 创建任务 需求评审", "create_task", {}, authorized=False)
    guard_mutation("在 PRJ-1001 创建任务 需求评审", "create_task", {})
    guard_mutation(None, "create_task", {}, authorized=False)


def test_plan_guard_authorized_only_for_hybrid_plans():
    def plan(details):
        return AgentCommandPlan(planning_details=details)

    assert plan_guard_authorized(plan(None)) is None
    assert (
        plan_guard_authorized(plan({"authorization": {"mode": "regex", "authorized": True}}))
        is None
    )
    assert (
        plan_guard_authorized(plan({"authorization": {"mode": "hybrid", "authorized": True}}))
        is True
    )
    assert (
        plan_guard_authorized(plan({"authorization": {"mode": "hybrid", "authorized": False}}))
        is False
    )


# --- tool groups ---------------------------------------------------------------------


def test_every_tool_is_core_or_in_exactly_one_group():
    grouped = [tool for toolset in TOOLSETS for tool in toolset.tools]
    assert len(grouped) == len(set(grouped))
    names = {tool.name for tool in MANAGEMENT_TOOLS}
    assert set(grouped) <= names
    core = {tool.name for tool in core_tools()}
    assert core | set(grouped) == names and not core & set(grouped)
    for toolset in TOOLSETS:
        assert toolset.instructions.strip()


def test_toolset_state_reset_and_inactive_error():
    state = ToolsetState(enabled=True)
    visible = {tool.name for tool in state.tools()}
    assert META_TOOL_NAME in visible and "propose_change" not in visible
    error = state.inactive_error("propose_change", tool_call_id="c1")
    assert error is not None and error.error.code == ToolErrorCode.TOOLSET_INACTIVE
    assert state.inactive_error("search_tasks", tool_call_id="c1") is None

    result = state.reset({"change_plan": True}, tool_call_id="c2")
    assert result.ok and result.data["activated"] == ["change_plan"]
    assert "propose_change" in {tool.name for tool in state.tools()}
    assert state.inactive_error("propose_change", tool_call_id="c3") is None

    state.reset({"branches": True}, tool_call_id="c4")
    assert state.active == ["branches"]
    assert not state.reset({"nope": True}, tool_call_id="c5").ok


def test_disabled_toolsets_equip_everything_and_inline_instructions():
    state = ToolsetState(enabled=False)
    assert len(state.tools()) == len(MANAGEMENT_TOOLS)
    assert state.inactive_error("propose_change", tool_call_id=None) is None
    messages = [ChatMessage(role="system", content="BASE"), ChatMessage(role="user", content="q")]
    assert with_toolset_prompt(messages, enabled=True) == messages
    merged = with_toolset_prompt(messages, enabled=False)
    assert merged[0].content.startswith("BASE") and full_toolset_prompt() in merged[0].content


@pytest.mark.asyncio
async def test_agentscope_toolkit_groups_match_toolsets():
    pytest.importorskip("agentscope")
    from app.agents.agentscope_tools import build_management_toolkit

    class Executor:
        execution_log: list = []

    def names(schemas):
        return {item.get("function", item).get("name") for item in schemas}

    flat = await build_management_toolkit(Executor()).get_tool_schemas()
    assert names(flat) == {tool.name for tool in MANAGEMENT_TOOLS}

    grouped = build_management_toolkit(Executor(), toolsets_enabled=True)
    basic = names(await grouped.get_tool_schemas())
    assert basic == {tool.name for tool in core_tools()} | {META_TOOL_NAME}
    active = names(await grouped.get_tool_schemas(groups=["change_plan"]))
    assert {tool for tool, group in GROUP_OF_TOOL.items() if group == "change_plan"} <= active


# --- AgentScope history --------------------------------------------------------------


def test_split_history_flattens_tool_exchange_and_keeps_latest_user():
    from app.agents.agentscope_runtime import _split_history_and_inbound

    rest = [
        ChatMessage(role="user", content="之前的问题"),
        ChatMessage(role="assistant", content="之前的回答"),
        ChatMessage(role="user", content="PRJ-1001 最近怎么样"),
        ChatMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="p1", name="get_project_progress_overview", arguments={})],
        ),
        ChatMessage(role="tool", content='{"ok": true}', tool_call_id="p1"),
    ]
    history, inbound = _split_history_and_inbound(rest, "fallback")
    assert inbound == "PRJ-1001 最近怎么样"
    assert all(item.role != "tool" and not item.tool_calls for item in history)
    assert history[-1].role == "assistant" and '{"ok": true}' in history[-1].content
    assert [item.content for item in history[:2]] == ["之前的问题", "之前的回答"]


# --- trace ---------------------------------------------------------------------------


def test_trace_pairs_tool_end_without_call_id():
    trace = AgentTrace(request_id=None, actor_id=None, actor_role="PROJECT_OWNER")
    for event in [
        AgentStreamEvent(event="tool_start", data={"tool": "a", "tool_call_id": "1"}),
        AgentStreamEvent(event="tool_start", data={"tool": "b", "tool_call_id": "2"}),
        AgentStreamEvent(event="tool_end", data={"tool": "a", "success": True}),
        AgentStreamEvent(event="tool_end", data={"tool": "b", "success": False, "error_code": "X"}),
        AgentStreamEvent(event="tool_end", data={"tool": "c", "tool_call_id": "9"}),
        AgentStreamEvent(event="delta", data={"content": "abc"}),
    ]:
        trace.observe(event)
    assert trace.tools_called == ["a", "b", "c"]
    assert [call.ok for call in trace.tool_calls] == [True, False, True]
    assert trace.tool_calls[1].error_code == "X"
    assert trace.reply_chars == 3


# --- legacy loop with tool groups ----------------------------------------------------


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def actor(db):
    user = User(
        name="示例负责人", username="owner", password_hash="unused", role=UserRole.PROJECT_OWNER
    )
    db.add(user)
    db.commit()
    return user


class ScriptedGateway:
    configured = True

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.offered: list[set[str]] = []

    async def chat_with_tools_stream(self, **kwargs):
        self.offered.append({tool.name for tool in kwargs["tools"]})
        step = self.rounds.pop(0)
        if isinstance(step, str):
            yield StreamDelta(content=step)
        else:
            yield StreamDelta(tool_calls=[step])


def scripted():
    return ScriptedGateway(
        [
            ToolCall(id="c1", name="get_change_proposal", arguments={"proposal_id": 1}),
            ToolCall(id="c2", name=META_TOOL_NAME, arguments={"change_plan": True}),
            "完成",
        ]
    )


@pytest.mark.asyncio
async def test_legacy_loop_requires_reset_tools_for_group_tools(db, actor):
    gateway = scripted()
    settings = Settings(_env_file=None, AGENT_TOOLSETS_ENABLED=True, AGENT_TRACE_LOG=False)
    agent = ManagementAgent(db, gateway=gateway, settings=settings)
    events = [event async for event in agent.chat_stream("看一下变更方案 1", actor=actor)]

    ends = [event.data for event in events if event.event == "tool_end"]
    assert ends[0]["error_code"] == ToolErrorCode.TOOLSET_INACTIVE.value
    assert ends[1]["success"] is True
    assert "get_change_proposal" not in gateway.offered[0]
    assert "get_change_proposal" in gateway.offered[2]
    trace = agent.last_trace
    assert trace.runtime == "legacy" and trace.toolsets_activated == ["change_plan"]
    assert trace.tools_called == ["get_change_proposal", META_TOOL_NAME]


@pytest.mark.asyncio
async def test_chat_matches_chat_stream(db, actor):
    settings = Settings(_env_file=None, AGENT_TOOLSETS_ENABLED=True, AGENT_TRACE_LOG=False)
    response = await ManagementAgent(db, gateway=scripted(), settings=settings).chat(
        "看一下变更方案 1", actor=actor
    )
    assert response.reply == "完成"
    assert response.tools_used == ["get_change_proposal", META_TOOL_NAME]
    assert len(response.tool_results) == 2
    assert response.llm_used


@pytest.mark.asyncio
async def test_planner_query_facts_with_dates_are_json_safe(db, actor):
    from datetime import date

    from app.agents.command_agent import command_stream
    from app.models.agent_conversation import AgentConversation
    from app.models.project import Project
    from app.models.task import Task
    from app.services.agent_idempotency import begin_request

    project = Project(project_code="PRJ-1001", project_name="示例项目", owner_id=actor.id)
    conversation = AgentConversation(user_id=actor.id, title="QA")
    db.add_all([project, conversation])
    db.flush()
    db.add(Task(project_id=project.id, task_name="上线检查", due_date=date(2026, 10, 9)))
    source = "把 PRJ-1001 上线检查的负责人改成示例负责人"
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="r1",
        content=source,
    )
    db.commit()

    class Planner:
        configured = True

        def __init__(self):
            self.rounds = 0

        async def chat_with_tools_stream(self, **kwargs):
            self.rounds += 1
            if self.rounds == 1:
                args = {
                    "entity": "task",
                    "filters": [{"field": "project_id", "op": "eq", "value": project.id}],
                    "fields": ["id", "title", "due_date"],
                }
                yield StreamDelta(
                    tool_calls=[ToolCall(id="q1", name="query_entities", arguments=args)]
                )
            else:
                raise RuntimeError("stop after facts")

    with pytest.raises(RuntimeError, match="stop after facts"):
        async for _ in command_stream(
            db, Planner(), Settings(_env_file=None), source, actor, request.id
        ):
            pass
    plan = db.scalar(select(AgentCommandPlan).where(AgentCommandPlan.request_id == request.id))
    assert plan.planning_details["facts"][0]["ok"] is True


def test_plan_rejects_unknown_update_fields(db, actor):
    from app.models.agent_conversation import AgentConversation
    from app.schemas.agent_command import CommandPlanInput
    from app.services.agent_commands import CommandService
    from app.services.agent_idempotency import begin_request
    from app.services.exceptions import DomainValidationError

    conversation = AgentConversation(user_id=actor.id, title="QA")
    db.add(conversation)
    db.flush()
    source = "需求评审完成度更新到 60%"
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="r3",
        content=source,
    )
    db.commit()

    def proposal(arguments):
        return CommandPlanInput.model_validate(
            {
                "items": [
                    {
                        "item_id": "u1",
                        "tool": "update_task",
                        "source_text": source,
                        "arguments": arguments,
                    }
                ]
            }
        )

    with pytest.raises(DomainValidationError, match="progress"):
        CommandService(db).create(
            request.id, source, proposal({"target_task_name": "需求评审", "progress": 60})
        )
    from app.models.agent_command import AgentCommandItem

    CommandService(db).create(
        request.id, source, proposal({"target_task_name": "需求评审", "progress_percent": 60})
    )
    item = db.scalar(select(AgentCommandItem))
    assert item.arguments["progress_percent"] == 60


def test_task_owner_may_restate_unchanged_core_fields(db, actor):
    from app.models.project import Project
    from app.models.task import Task
    from app.services.exceptions import PermissionDeniedError
    from app.services.management_write import ManagementWriteService

    member = User(name="测试甲", username="member_a", password_hash="unused", role=UserRole.MEMBER)
    other = User(name="测试乙", username="member_b", password_hash="unused", role=UserRole.MEMBER)
    db.add_all([member, other])
    db.flush()
    project = Project(project_code="PRJ-1001", project_name="示例项目", owner_id=actor.id)
    db.add(project)
    db.flush()
    task = Task(project_id=project.id, task_name="需求评审", owner_id=member.id)
    db.add(task)
    db.commit()

    service = ManagementWriteService(db)
    result = service.update_task(
        member, {"task_id": task.id, "owner_id": member.id, "progress_percent": 60}
    )
    assert result["task"]["progress_percent"] == 60
    with pytest.raises(PermissionDeniedError):
        service.update_task(member, {"task_id": task.id, "owner_id": other.id})


def test_batch_create_argument_errors_mirror_execution_rules():
    from app.services.agent_batch import batch_create_argument_errors

    assert batch_create_argument_errors({"items": [{"name": "需求评审"}]}) == []
    assert (
        batch_create_argument_errors({"tasks": [{"task_name": "A", "owner_names": ["测试甲"]}]})
        == []
    )
    errors = batch_create_argument_errors(
        {
            "items": [
                {"task_name": "A", "note": "x"},
                {"owner_names": []},
                {"task_name": "B", "milestone": 1},
            ]
        }
    )
    assert len(errors) == 3
    assert "note" in errors[0] and "task_name" in errors[1] and "create_milestone" in errors[2]


@pytest.mark.asyncio
async def test_planner_repairs_unknown_batch_fields_before_execution(db, actor):
    from app.agents.command_agent import command_stream
    from app.models.agent_conversation import AgentConversation
    from app.models.project import Project
    from app.services.agent_idempotency import begin_request

    project = Project(project_code="PRJ-1001", project_name="示例项目", owner_id=actor.id)
    conversation = AgentConversation(user_id=actor.id, title="QA")
    db.add_all([project, conversation])
    db.flush()
    source = "在 PRJ-1001 创建任务 接口自测"
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="r2",
        content=source,
    )
    db.commit()

    def plan(row):
        return {
            "items": [
                {
                    "item_id": "t1",
                    "tool": "batch_create_tasks",
                    "source_text": "创建任务 接口自测",
                    "arguments": {"project_id": project.id, "items": [row]},
                }
            ]
        }

    class Planner:
        configured = True

        def __init__(self):
            self.feedback: list[str] = []
            self.proposals = [
                plan({"task_name": "接口自测", "note": "多余"}),
                plan({"task_name": "接口自测"}),
            ]

        async def chat_with_tools_stream(self, **kwargs):
            last = kwargs["messages"][-1]
            if last.role == "tool":
                self.feedback.append(last.content or "")
            proposal = self.proposals.pop(0)
            yield StreamDelta(
                tool_calls=[ToolCall(id="p", name="plan_commands", arguments=proposal)]
            )

    planner = Planner()
    async for _ in command_stream(db, planner, Settings(_env_file=None), source, actor, request.id):
        pass
    assert planner.feedback and "note" in planner.feedback[0]
    from app.models.agent_command import AgentCommandItem

    items = list(db.scalars(select(AgentCommandItem)))
    assert [item.arguments["items"] for item in items] == [[{"task_name": "接口自测"}]]


# --- eval harness --------------------------------------------------------------------


def test_core_eval_cases_load():
    cases = load_cases([BACKEND / "evals" / "assistant_core.yaml"])
    assert len(cases) >= 30
    assert len({case.id for case in cases}) == len(cases)
    assert all("writes" in case.expect for case in cases)


def test_score_agent_flags_unauthorized_writes_and_tool_limits():
    trace = AgentTrace(request_id=None, actor_id=None, actor_role="PROJECT_OWNER", route="react")
    trace.observe(AgentStreamEvent(event="tool_start", data={"tool": "create_task"}))
    failures = score_agent(
        {
            "writes": False,
            "tools_forbid": ["create_task"],
            "max_tool_calls": 0,
            "route_in": ["react"],
        },
        delta={"task": 1},
        trace=trace,
        reply="",
        status="COMPLETED",
    )
    assert any("unauthorized" in item for item in failures)
    assert any("forbidden" in item for item in failures)
    assert any("tool calls" in item for item in failures)

    primed = AgentTrace(request_id=None, actor_id=None, actor_role="PROJECT_OWNER")
    primed.primed_tools = ["get_project_progress_overview"]
    expect = {"tools_require_any": ["get_project_progress_overview"]}
    assert not score_agent(expect, delta={}, trace=primed, reply="", status=None)
    assert not score_agent(
        {"writes": True, "created": {"task": 1}},
        delta={"task": 1},
        trace=trace,
        reply="",
        status=None,
    )
