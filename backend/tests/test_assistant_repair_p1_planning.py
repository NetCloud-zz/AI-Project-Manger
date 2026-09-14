"""P1 assistant repair: query phase, budget, intent/authorization split."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.agents.command_agent import PlanningBudget, command_stream
from app.core.config import Settings
from app.core.database import Base
from app.llm.schemas import StreamDelta, ToolCall
from app.models.agent_conversation import AgentConversation
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.services.agent_commands import CommandService
from app.services.agent_idempotency import begin_request


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
        name="测试甲",
        username="p1_owner",
        password_hash="unused",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    return user


class RoundGateway:
    configured = True

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []
        self.tools_seen = []

    async def chat_with_tools_stream(self, **kwargs):
        self.calls.append(list(kwargs["messages"]))
        self.tools_seen.append([tool.name for tool in kwargs.get("tools") or []])
        proposal = self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]
        if isinstance(proposal, Exception):
            raise proposal
        if isinstance(proposal, list):
            yield StreamDelta(tool_calls=proposal)
            return
        yield StreamDelta(
            tool_calls=[
                ToolCall(
                    id=f"plan-{len(self.calls)}",
                    name="plan_commands",
                    arguments=proposal,
                )
            ]
        )


def prepare(db, actor, source: str):
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=actor.id)
    conversation = AgentConversation(user_id=actor.id, title="P1")
    db.add_all([project, conversation])
    db.flush()
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="p1-request",
        content=source,
    )
    db.commit()
    return request, project


@pytest.mark.asyncio
async def test_planning_query_phase_registers_facts_before_plan(db, actor):
    source = "在项目 PRJ-1001 中创建任务：方案评审 —— 测试甲"
    request, project = prepare(db, actor, source)
    items = [
        {
            "item_id": "owners",
            "tool": "batch_find_users",
            "source_text": "核对负责人：测试甲",
            "arguments": {"names": ["测试甲"]},
        },
        {
            "item_id": "task",
            "tool": "create_task",
            "source_text": "创建任务：方案评审 —— 测试甲",
            "depends_on": ["owners"],
            "arguments": {
                "project_id": project.id,
                "task_name": "方案评审",
                "owner_id": actor.id,
            },
        },
    ]
    gateway = RoundGateway(
        [ToolCall(id="q1", name="batch_find_users", arguments={"names": ["测试甲"]})],
        {"items": items},
    )
    events = [
        e
        async for e in command_stream(
            db, gateway, Settings(_env_file=None), source, actor, request.id
        )
    ]
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "COMPLETED"
    assert plan.planning_details["facts"]
    assert plan.planning_details["facts"][0]["tool"] == "batch_find_users"
    assert any(e.event == "tool_end" for e in events)
    assert "batch_find_users" in gateway.tools_seen[0]
    assert "plan_commands" in gateway.tools_seen[0]
    assert db.scalar(select(func.count()).select_from(Task)) == 1


@pytest.mark.asyncio
async def test_planning_repairs_write_tools_then_accepts_plan(db, actor):
    source = "创建任务：方案评审 —— 测试甲"
    request, project = prepare(db, actor, source)
    items = [
        {
            "item_id": "task",
            "tool": "create_task",
            "source_text": "创建任务：方案评审 —— 测试甲",
            "arguments": {
                "project_id": project.id,
                "task_name": "方案评审",
                "owner_id": actor.id,
            },
        }
    ]
    gateway = RoundGateway(
        [ToolCall(id="w1", name="create_task", arguments={"task_name": "方案评审"})],
        {"items": items},
    )
    events = [
        e
        async for e in command_stream(
            db, gateway, Settings(_env_file=None), source, actor, request.id
        )
    ]
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "COMPLETED"
    assert any(
        err.get("message") == "规划阶段禁止调用写入工具"
        for attempt in plan.planning_details["attempts"]
        for err in attempt.get("errors") or []
    )
    assert len(gateway.calls) >= 2
    assert any(
        "禁止直接调用写入工具" in str(m.content)
        for msgs in gateway.calls[1:]
        for m in msgs
        if m.role == "user"
    )
    assert db.scalar(select(func.count()).select_from(Task)) == 1
    assert not any("不能直接写入" in str(e.data) for e in events)


@pytest.mark.asyncio
async def test_planning_rejects_write_tools_after_repair_budget(db, actor):
    source = "创建任务：方案评审 —— 测试甲"
    request, _ = prepare(db, actor, source)
    write = [ToolCall(id="w1", name="create_task", arguments={"task_name": "方案评审"})]
    gateway = RoundGateway(write, write, write, write)
    events = [
        e
        async for e in command_stream(
            db, gateway, Settings(_env_file=None), source, actor, request.id
        )
    ]
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "INVALID_PLAN"
    assert plan.planning_details["error_code"] == "COMMAND_PLAN_INVALID"
    assert db.scalar(select(func.count()).select_from(Task)) == 0
    assert any("不能直接写入" in str(e.data) for e in events)
    assert len(plan.planning_details["attempts"]) >= 2


def test_planning_budget_stops_repeated_same_error():
    budget = PlanningBudget(
        max_rounds=6, max_query_calls=8, max_repair_attempts=3, max_same_error=2
    )
    assert budget.begin_round()
    assert budget.note_repair("x") is True
    assert budget.begin_round()
    assert budget.note_repair("x") is False
    assert budget.stop_reason == "COMMAND_BUDGET_SAME_ERROR"
