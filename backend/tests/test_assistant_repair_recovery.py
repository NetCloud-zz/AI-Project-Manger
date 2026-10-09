"""Recovery after cancel / interrupt / stale reclaim; requirement inventory."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.agent_command import AgentCommandItem, AgentCommandPlan
from app.models.agent_conversation import AgentConversation, AgentMessage, MessageRole, MessageStatus
from app.models.agent_request import AgentRequest, AgentRequestStatus
from app.models.user import User, UserRole
from app.schemas.agent_command import CommandPlanInput
from app.services.agent_commands import CommandService, build_requirement_inventory
from app.services.agent_idempotency import begin_request
from app.services.conversation import ConversationService


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
        username="recovery_owner",
        password_hash="unused",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    return user


def _request(db, actor, content="创建任务 A"):
    conversation = AgentConversation(user_id=actor.id, title="recovery")
    db.add(conversation)
    db.flush()
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="recovery-1",
        content=content,
    )
    db.commit()
    return request, content


def test_build_requirement_inventory_for_batch_and_single_create():
    proposal = CommandPlanInput(
        items=[
            {
                "item_id": "batch",
                "tool": "batch_create_tasks",
                "source_text": "创建任务",
                "arguments": {
                    "items": [
                        {
                            "client_item_id": "t1",
                            "task_name": "方案评审",
                            "owner_name": "测试甲",
                            "planned_duration_days": 5,
                        },
                        {"client_item_id": "t2", "task_name": "实施推进"},
                    ]
                },
            },
            {
                "item_id": "proj",
                "tool": "create_project",
                "source_text": "创建项目",
                "arguments": {"project_name": "演示项目"},
            },
        ]
    )
    inventory = build_requirement_inventory(proposal)
    assert len(inventory) == 3
    assert inventory[0]["requirement_id"] == "req_batch_t1"
    assert inventory[0]["fields"]["planned_duration_days"] == 5
    assert inventory[2]["kind"] == "project"


def test_reconcile_planning_interrupt_keeps_source(db, actor):
    request, source = _request(db, actor)
    service = CommandService(db)
    plan = service.start(request.id, source, actor)
    request.status = AgentRequestStatus.INTERRUPTED
    db.commit()
    reconciled = service.reconcile_after_interrupt(request.id, reason="interrupted")
    assert reconciled is not None
    assert reconciled.status == "PLANNING_FAILED"
    snapshot = service.snapshot(reconciled)
    assert snapshot["unplanned"] is True
    assert snapshot["source"] == source
    assert snapshot["recovery"]["action"] == "restore_source"


def test_reconcile_running_plan_pauses_pending_and_marks_unknown(db, actor):
    request, source = _request(db, actor)
    plan = AgentCommandPlan(
        request_id=request.id,
        source=source,
        status="RUNNING",
        policy="independent",
        expected_count=2,
        revision=1,
    )
    db.add(plan)
    db.flush()
    db.add_all(
        [
            AgentCommandItem(
                plan_id=plan.id,
                ordinal=0,
                item_id="t0",
                tool="create_task",
                source_text="A",
                source_start=0,
                source_end=1,
                arguments={},
                depends_on=[],
                state="SUCCEEDED",
            ),
            AgentCommandItem(
                plan_id=plan.id,
                ordinal=1,
                item_id="t1",
                tool="create_task",
                source_text="B",
                source_start=0,
                source_end=1,
                arguments={},
                depends_on=[],
                state="RUNNING",
            ),
            AgentCommandItem(
                plan_id=plan.id,
                ordinal=2,
                item_id="t2",
                tool="create_task",
                source_text="C",
                source_start=0,
                source_end=1,
                arguments={},
                depends_on=[],
                state="PENDING",
            ),
        ]
    )
    db.commit()
    service = CommandService(db)
    reconciled = service.reconcile_after_interrupt(request.id, reason="stale_reclaim")
    assert reconciled.status == "PAUSED"
    states = {item.item_id: item.state for item in service.items(reconciled)}
    assert states["t0"] == "SUCCEEDED"
    assert states["t1"] == "UNKNOWN"
    assert states["t2"] == "PENDING"
    snapshot = service.snapshot(reconciled)
    assert snapshot["recovery"]["action"] == "manual_verify"
    assert "t1" in snapshot["recovery"]["item_ids"]


def test_finalize_streaming_reconciles_running_plan(db, actor):
    request, source = _request(db, actor)
    conversation = db.get(AgentConversation, request.conversation_id)
    assistant = AgentMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="",
        status=MessageStatus.STREAMING,
    )
    db.add(assistant)
    db.flush()
    request.assistant_message_id = assistant.id
    request.status = AgentRequestStatus.RUNNING
    plan = AgentCommandPlan(
        request_id=request.id,
        source=source,
        status="RUNNING",
        policy="independent",
        expected_count=1,
    )
    db.add(plan)
    db.flush()
    db.add(
        AgentCommandItem(
            plan_id=plan.id,
            ordinal=0,
            item_id="t0",
            tool="create_task",
            source_text="A",
            source_start=0,
            source_end=1,
            arguments={},
            depends_on=[],
            state="PENDING",
        )
    )
    db.commit()
    ConversationService(db).finalize_streaming_message(assistant.id, interrupted=True)
    refreshed = CommandService(db).owned(request.id, actor)
    assert refreshed.status == "PAUSED"
    assert CommandService(db).snapshot(refreshed)["recovery"]["action"] == "retry_pending"
