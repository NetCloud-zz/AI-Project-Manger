"""Planning regression: numbered bulk requests, diagnostics, effects and recovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.agents.command_agent import PLAN_TOOL, command_stream
from app.agents.management_agent import ManagementAgent
from app.core.config import Settings
from app.core.database import Base
from app.llm.base import LLMError
from app.llm.schemas import StreamDelta, ToolCall
from app.models.agent_command import AgentCommandPlan
from app.models.agent_conversation import AgentConversation, AgentMessage, MessageStatus
from app.models.agent_request import AgentRequest, AgentRequestStatus
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.schemas.agent import MessageCreate
from app.schemas.agent_command import CommandPlanInput, CommandRetryInput, validate_coverage
from app.services.agent_commands import CommandService, command_error_code, format_execution
from app.services.agent_idempotency import begin_request
from app.services.conversation import ConversationService
from app.services.exceptions import DomainValidationError


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
        name="测试负责人", username="qa_owner", password_hash="unused", role=UserRole.PROJECT_OWNER
    )
    db.add(user)
    db.commit()
    return user


def setup(db, actor, count=3):
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=actor.id)
    conversation = AgentConversation(user_id=actor.id, title="QA")
    db.add_all([project, conversation])
    db.flush()
    source = f"创建{count}个任务\n" + "\n".join(f"{i}. 创建任务 QA-{i}" for i in range(count))
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="qa-request",
        content=source,
    )
    db.commit()
    items = [
        {
            "item_id": f"t{i}",
            "tool": "create_task",
            "source_text": f"创建任务 QA-{i}",
            "arguments": {"project_id": project.id, "task_name": f"QA-{i}", "owner_id": actor.id},
        }
        for i in range(count)
    ]
    return request, source, items


class Gateway:
    configured = True

    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls = []

    async def chat_with_tools_stream(self, **kwargs):
        self.calls.append(list(kwargs["messages"]))
        proposal = self.plans[min(len(self.calls) - 1, len(self.plans) - 1)]
        if isinstance(proposal, Exception):
            raise proposal
        yield StreamDelta(
            tool_calls=[
                ToolCall(id=f"plan-{len(self.calls)}", name="plan_commands", arguments=proposal)
            ]
        )


async def collect(db, actor, request, source, gateway):
    return [
        e
        async for e in command_stream(
            db, gateway, Settings(_env_file=None), source, actor, request.id
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [None, 0, 26, 999])
async def test_25_rows_wrong_declared_count_does_not_fail(db, actor, declared):
    request, source, items = setup(db, actor, 25)
    proposal = {"items": items}
    if declared is not None:
        proposal["expected_count"] = declared
    gateway = Gateway(proposal)
    events = await collect(db, actor, request, source, gateway)
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "COMPLETED"
    assert plan.expected_count == 25
    assert db.scalar(select(func.count()).select_from(Task)) == 25
    assert len(gateway.calls) == 1
    assert plan.planning_details["attempts"][0]["declared_count"] == declared
    assert not any("validation error" in str(e.data) for e in events)


def test_model_schema_does_not_request_count():
    assert "expected_count" not in PLAN_TOOL.parameters["properties"]


@pytest.mark.asyncio
async def test_missing_row_repair_receives_original_candidate_and_coverage(db, actor):
    request, source, items = setup(db, actor)
    gateway = Gateway({"items": items[:2]}, {"items": items})
    await collect(db, actor, request, source, gateway)
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "COMPLETED"
    assert len(plan.planning_details["attempts"]) == 2
    assert plan.planning_details["attempts"][0]["errors"]
    assert any(m.role == "assistant" and m.tool_calls for m in gateway.calls[1])
    assert any(m.role == "tool" and "actual_count" in m.content for m in gateway.calls[1])


@pytest.mark.asyncio
async def test_failed_plan_keeps_evidence_without_developer_errors(db, actor):
    request, source, items = setup(db, actor)
    gateway = Gateway({"items": items[:2]})
    events = await collect(db, actor, request, source, gateway)
    service = CommandService(db)
    plan = service.owned(request.id, actor)
    snapshot = service.snapshot(plan)
    assert plan.status == "INVALID_PLAN"
    assert snapshot["business_item_count"] == snapshot["remaining"] == 0
    assert snapshot["source"] == source
    assert snapshot["planned_step_count"] == 0
    assert len(plan.planning_details["attempts"]) == 2
    assert db.scalar(select(func.count()).select_from(Task)) == 0
    assert "pydantic" not in str([e.data for e in events])
    assert command_error_code([snapshot]) == "COMMAND_PLAN_INVALID"
    with pytest.raises(DomainValidationError):
        service.retry(plan, CommandRetryInput(expected_revision=plan.revision, item_ids=["t0"]))


@pytest.mark.asyncio
async def test_project_owner_text_reaches_model_without_format_preflight(db, actor):
    request, _, _ = setup(db, actor, 25)
    source = "按以下内容创建：\n项目：综合交付项目\n负责人：待填写\n" + "\n".join(
        f"{i}. 任务{i} —— 负责人待定 —— 日期待定" for i in range(25)
    )
    gateway = Gateway({})
    await collect(db, actor, request, source, gateway)
    service = CommandService(db)
    snapshot = service.snapshot(service.owned(request.id, actor))
    assert snapshot["status"] == "INVALID_PLAN"
    assert snapshot["business_item_count"] == 0
    assert snapshot["source"] == source
    assert gateway.calls
    assert any(m.role == "user" and m.content == source for m in gateway.calls[0])
    assert db.scalar(select(func.count()).select_from(Task)) == 0


@pytest.mark.asyncio
async def test_model_timeout_is_terminal_and_sanitized(db, actor):
    request, source, _ = setup(db, actor)
    events = await collect(db, actor, request, source, Gateway(LLMError("secret diagnostic")))
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "PLANNING_FAILED"
    assert "secret diagnostic" not in str([e.data for e in events])


@pytest.mark.asyncio
async def test_timeout_retries_then_succeeds(db, actor):
    request, source, items = setup(db, actor)
    gateway = Gateway(TimeoutError(), {"items": items})
    await collect(db, actor, request, source, gateway)
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "COMPLETED"
    assert len(gateway.calls) == 2
    assert db.scalar(select(func.count()).select_from(Task)) == 3


def test_whitespace_tolerant_source_text_mapping(db, actor):
    _, source, items = setup(db, actor)
    items[0]["source_text"] = "创建任务\nQA-0"
    assert "创建任务 QA-0" in source or "创建任务 QA-0" in source.replace("\n", " ")
    # Exact line in setup is "创建任务 QA-0" without newline between 任务 and QA
    items[0]["source_text"] = "创建任务  QA-0"
    spans = validate_coverage(CommandPlanInput(items=items), source)
    assert spans[0][0] >= 0


def test_create_project_query_only_plan_rejected(db, actor):
    source = (
        "请创建项目： 项目名称：DEMO 项目 目标：演示 "
        "负责人：示例甲 开始：2026-08-13 目标完成：2026-10-06"
    )
    items = [
        {
            "item_id": "owners",
            "tool": "batch_find_users",
            "source_text": "负责人：示例甲",
            "arguments": {"names": ["示例甲"]},
        },
        {
            "item_id": "existing",
            "tool": "list_projects",
            "source_text": "请创建项目： 项目名称：DEMO 项目",
            "arguments": {},
        },
    ]
    with pytest.raises(ValueError, match="create_project"):
        validate_coverage(CommandPlanInput(items=items), source)


def test_flattened_task_quote_with_newlines_in_model_output():
    source = (
        "然后创建任务： 一、药物化学（阶段） "
        "1. 中间体合成（三环） —— 示例甲 —— 2026-08-28 ~ 2026-09-28 "
        "2. OPS-26510 —— 示例乙 —— 2026-08-13 ~ 2026-08-30"
    )
    items = [
        {
            "item_id": "owners",
            "tool": "batch_find_users",
            "source_text": "一、药物化学（阶段）\n1. 中间体合成（三环） —— 示例甲 —— 2026-08-28 ~ 2026-09-28",
            "arguments": {"names": ["示例甲", "示例乙"]},
        },
        {
            "item_id": "batch",
            "tool": "batch_create_tasks",
            "source_text": source,
            "depends_on": ["owners"],
            "arguments": {
                "project_code": "DEMO",
                "tasks": [
                    {"task_name": "中间体合成（三环）", "owner_name": "示例甲"},
                    {"task_name": "OPS-26510", "owner_name": "示例乙"},
                ],
            },
        },
    ]
    spans = validate_coverage(CommandPlanInput(items=items), source)
    assert len(spans) == 2


def test_shared_source_can_authorize_distinct_tasks(db, actor):
    _, source, items = setup(db, actor)
    for item in items:
        item["source_text"] = source
    assert len(validate_coverage(CommandPlanInput(items=items), source)) == 3


def test_cycles_and_invalid_dependencies_remain_rejected(db, actor):
    _, _, items = setup(db, actor)
    items[0]["depends_on"] = ["t1"]
    items[1]["depends_on"] = ["t0"]
    with pytest.raises(ValueError, match="有环"):
        CommandPlanInput(items=items)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False])
async def test_conversation_failure_not_completed(db, actor, stream):
    service = ConversationService(db)
    conversation = service.create_conversation(actor)
    gateway = Gateway({"items": []})

    def factory(db, settings=None):
        return ManagementAgent(db, gateway=gateway, settings=Settings(_env_file=None))

    with patch("app.services.conversation.ManagementAgent", side_effect=factory):
        if stream:
            events = [
                e
                async for e in service.stream_message(
                    conversation.id,
                    MessageCreate(content="创建3个任务", client_request_id="failure-1"),
                    actor=actor,
                )
            ]
            assert [e for e in events if e.event == "done"][-1].data["status"] == "FAILED"
        else:
            await service.send_message(
                conversation.id, MessageCreate(content="创建3个任务"), actor=actor
            )
    message = db.scalar(select(AgentMessage).order_by(AgentMessage.id.desc()))
    request = db.scalar(select(AgentRequest).order_by(AgentRequest.id.desc()))
    assert message.status == MessageStatus.FAILED
    assert request.status == AgentRequestStatus.FAILED
    assert request.error_code == "COMMAND_PLAN_INVALID"


@pytest.mark.asyncio
async def test_missing_reference_is_recorded_not_raised(db, actor):
    request, source, items = setup(db, actor, 2)
    items[1]["depends_on"] = ["t0"]
    items[1]["arguments"]["project_id"] = {"$ref": "t0.missing.id"}
    await collect(db, actor, request, source, Gateway({"items": items}))
    service = CommandService(db)
    snapshot = service.snapshot(service.owned(request.id, actor))
    assert snapshot["succeeded"] == 1
    assert snapshot["items"][1]["state"] == "FAILED"


@pytest.mark.asyncio
async def test_reexecution_cannot_overwrite_completed_plan(db, actor):
    request, source, items = setup(db, actor, 1)
    await collect(db, actor, request, source, Gateway({"items": items}))
    with pytest.raises(DomainValidationError):
        await collect(db, actor, request, source, Gateway({"items": items}))
    assert db.scalar(select(func.count()).select_from(Task)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("atomic", [True, False])
async def test_validation_failure_does_not_leave_atomic_partial_writes(db, actor, atomic):
    request, source, items = setup(db, actor)
    items[1]["arguments"]["owner_id"] = 999999
    if atomic:
        source += "\n要么全部成功，否则全部回滚"
    await collect(
        db,
        actor,
        request,
        source,
        Gateway({"items": items, "policy": "atomic" if atomic else "independent"}),
    )
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == ("FAILED" if atomic else "PARTIAL")
    assert db.scalar(select(func.count()).select_from(Task)) == (0 if atomic else 2)


@pytest.mark.asyncio
async def test_stop_inside_atomic_batch_rolls_back(db, actor, monkeypatch):
    from app.agents.management_tools import ManagementToolExecutor

    request, source, items = setup(db, actor)
    source += "\n要么全部成功，否则全部回滚"
    original = ManagementToolExecutor.execute_result

    def stop_after_first(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        request.cancel_requested = True
        return result

    monkeypatch.setattr(ManagementToolExecutor, "execute_result", stop_after_first)
    await collect(db, actor, request, source, Gateway({"items": items, "policy": "atomic"}))
    assert db.scalar(select(func.count()).select_from(Task)) == 0
    assert CommandService(db).owned(request.id, actor).status != "COMPLETED"


@pytest.mark.asyncio
async def test_budget_resume_skips_successful_items(db, actor):
    request, source, items = setup(db, actor)
    service = CommandService(db)
    plan = service.create(request.id, source, CommandPlanInput(items=items))
    result = await service.run(plan, actor, budget=1)
    assert result["succeeded"] == 1
    revision = result["revision"]
    service.retry(plan, CommandRetryInput(expected_revision=revision, item_ids=["t1", "t2"]))
    with pytest.raises(DomainValidationError):
        service.retry(plan, CommandRetryInput(expected_revision=revision, item_ids=["t1", "t2"]))
    result = await service.run(plan, actor)
    assert result["succeeded"] == 3
    assert [i["attempts"] for i in result["items"]] == [1, 1, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", [UserRole.ADMIN, UserRole.EXECUTIVE, UserRole.PROJECT_OWNER, UserRole.MEMBER]
)
async def test_planning_does_not_bypass_role_permissions(db, actor, role):
    request, source, items = setup(db, actor, 1)
    actor.role = role
    db.commit()
    await collect(db, actor, request, source, Gateway({"items": items}))
    # The actor owns the project, so only the read-only EXECUTIVE role is refused.
    assert db.scalar(select(func.count()).select_from(Task)) == (
        0 if role == UserRole.EXECUTIVE else 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.PROJECT_OWNER, UserRole.MEMBER])
async def test_planning_refuses_non_owner_of_project(db, actor, role):
    request, source, items = setup(db, actor, 1)
    other = User(name="其他负责人", username="qa_other", password_hash="unused", role=role)
    db.add(other)
    db.flush()
    project = db.scalar(select(Project).where(Project.project_code == "PRJ-1001"))
    project.owner_id = other.id
    actor.role = role
    db.commit()
    await collect(db, actor, request, source, Gateway({"items": items}))
    assert db.scalar(select(func.count()).select_from(Task)) == 0


def test_failure_legacy_card_is_readable_without_raw_exception(db, actor):
    request, source, _ = setup(db, actor)
    plan = AgentCommandPlan(
        request_id=request.id,
        source=source,
        status="INVALID_PLAN",
        expected_count=0,
        error="1 validation error for CommandPlanInput https://errors.pydantic.dev",
    )
    db.add(plan)
    db.commit()
    result = CommandService(db).snapshot(plan)
    assert result["business_item_count"] == result["remaining"] == 0
    assert result["source"] == source
    assert result["source"] == source
    assert "pydantic" not in result["error"]


def test_candidates_are_recursively_sanitized():
    from app.agents.command_agent import safe_candidate

    assert safe_candidate(
        {"items": [{"arguments": {"password": "never store", "task_name": "QA"}}]}
    ) == {"items": [{"arguments": {"task_name": "QA"}}]}


@pytest.mark.asyncio
async def test_cancel_waits_for_workers_to_settle():
    import asyncio

    from app.services.agent_commands import settled_workers

    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def worker():
        started.set()
        await release.wait()
        finished.set()

    task = asyncio.create_task(settled_workers(worker()))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_interrupted_planning_can_be_restored(db, actor):
    request, source, _ = setup(db, actor)
    service = CommandService(db)
    plan = service.start(request.id, source, actor)
    request.status = AgentRequestStatus.INTERRUPTED
    db.commit()
    snapshot = service.snapshot(plan)
    assert snapshot["status"] == "PLANNING_FAILED"
    assert snapshot["source"] == source


@pytest.mark.asyncio
async def test_plan_api_ownership_and_invalid_retry(db, actor):
    import httpx

    from app.core.database import get_db
    from app.core.deps import get_current_user
    from app.main import create_app

    request, source, items = setup(db, actor)
    await collect(db, actor, request, source, Gateway({"items": items[:1]}))
    app = create_app()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: actor
    # Explicit timeout + generator override: avoids ASGI/session hangs seen with
    # bare `lambda: db` overrides and unbounded client waits.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        timeout=10.0,
    ) as client:
        result = await client.get(f"/api/v1/agent/requests/{request.id}/plan")
        assert result.status_code == 200
        body = result.json()
        assert body["source"] == source
        assert "attempts" not in body
        assert "recovery" in body
        retry = await client.post(
            f"/api/v1/agent/requests/{request.id}/plan/retry",
            json={"expected_revision": 1, "item_ids": ["t0"]},
        )
        assert retry.status_code == 409
        other = User(id=999, name="Other", username="other", role=UserRole.ADMIN)
        app.dependency_overrides[get_current_user] = lambda: other
        assert (await client.get(f"/api/v1/agent/requests/{request.id}/plan")).status_code == 404


@pytest.mark.asyncio
async def test_stringified_items_execute_once(db, actor):
    import json

    request, source, items = setup(db, actor)
    gateway = Gateway({"items": json.dumps(items)})
    await collect(db, actor, request, source, gateway)
    assert len(gateway.calls) == 1
    assert db.scalar(select(func.count()).select_from(Task)) == 3
    assert db.get(AgentRequest, request.id).heartbeat_at is not None


@pytest.mark.parametrize("encoded", ["{}", "null", "[]", '[{"tool":"create_task"}]', "broken"])
def test_stringified_invalid_items_still_rejected(encoded):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CommandPlanInput.model_validate({"items": encoded})


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ["markdown", "flattened", "prose", "table", "json"])
@pytest.mark.parametrize("batched", [False, True])
async def test_free_form_bulk_input_reaches_model_unchanged_and_plans(db, actor, layout, batched):
    import json

    request, _, items = setup(db, actor, 25)
    blocks = [
        f"{i % 7 + 1}. **创建任务 QA-{i}**\n"
        "  * 负责人：待定\n  * 协作人：待定\n"
        "  * 时间：待定\n  * 计划周期：28 天"
        for i in range(25)
    ]
    if layout in {"markdown", "flattened"}:
        source = "该项目下： # 创建任务\n## 一、交付（阶段）\n" + "\n".join(blocks)
        if layout == "flattened":
            source = source.replace("\n", " ")
    elif layout == "prose":
        source = "请在该项目下" + "，然后".join(
            f"创建任务 QA-{i}，负责人和日期待定" for i in range(25)
        )
    elif layout == "table":
        source = "创建任务\n| 工作内容 | 负责人 | 日期 |\n|---|---|---|\n" + "\n".join(
            f"| 创建任务 QA-{i} | 待定 | 待定 |" for i in range(25)
        )
    else:
        source = json.dumps(
            {
                "指令": "创建任务",
                "内容": [{"任务": f"创建任务 QA-{i}", "负责人": "待定"} for i in range(25)],
            },
            ensure_ascii=False,
        )
    for item in items:
        item["arguments"].pop("owner_id")
    if batched:
        items = [
            {
                "item_id": "batch",
                "tool": "batch_create_tasks",
                "source_text": source,
                "arguments": {
                    "project_id": items[0]["arguments"]["project_id"],
                    "operation_id": "qa-free-form-batch",
                    "items": [
                        {
                            "client_item_id": item["item_id"],
                            "task_name": item["arguments"]["task_name"],
                        }
                        for item in items
                    ],
                },
            }
        ]
    gateway = Gateway({"items": items})
    events = await collect(db, actor, request, source, gateway)
    assert any(m.role == "user" and m.content == source for m in gateway.calls[0])
    assert len(gateway.calls) == 1
    ready = next(e.data for e in events if e.event == "card" and e.data["status"] == "READY")
    if batched:
        assert len(ready["items"]) == 1
        assert len(ready["items"][0]["arguments"]["items"]) == 25
        # SQLite intentionally refuses specialized batch execution; planning
        # must succeed, and this storage limitation must remain explicit.
        service = CommandService(db)
        step = service.items(service.owned(request.id, actor))[0]
        assert step.result["error"]["code"] == "PLAN_REQUIRED"
        assert db.scalar(select(func.count()).select_from(Task)) == 0
        return
    assert CommandService(db).owned(request.id, actor).status == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(Task)) == 25


@pytest.mark.asyncio
async def test_silent_planning_ticks_close_gateway():
    import asyncio
    from contextlib import aclosing

    from app.agents.command_agent import planning_ticks

    closed = asyncio.Event()

    async def silent():
        try:
            await asyncio.Event().wait()
            yield StreamDelta()
        finally:
            closed.set()

    async with aclosing(planning_ticks(silent(), interval=0.01)) as ticks:
        assert await anext(ticks) is None
        assert await asyncio.wait_for(anext(ticks), timeout=1) is None
    assert closed.is_set()


@pytest.mark.asyncio
async def test_disconnect_during_planning_is_terminal(db, actor):
    from contextlib import aclosing

    request, source, items = setup(db, actor)
    async with aclosing(
        command_stream(
            db, Gateway({"items": items}), Settings(_env_file=None), source, actor, request.id
        )
    ) as stream:
        assert (await anext(stream)).event == "heartbeat"
    plan = CommandService(db).owned(request.id, actor)
    assert plan.status == "PLANNING_FAILED"
    assert plan.planning_details["error_code"] == "COMMAND_INTERRUPTED"
    assert db.scalar(select(func.count()).select_from(Task)) == 0


@pytest.mark.asyncio
async def test_cancel_silent_planning_closes_model_and_records_failure(db, actor):
    import asyncio

    entered, closed = asyncio.Event(), asyncio.Event()

    class SilentGateway:
        async def chat_with_tools_stream(self, **kwargs):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield StreamDelta()
            finally:
                closed.set()

    request, source, _ = setup(db, actor)
    running = asyncio.create_task(collect(db, actor, request, source, SilentGateway()))
    await asyncio.wait_for(entered.wait(), timeout=1)
    assert db.get(AgentRequest, request.id).heartbeat_at is not None
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert closed.is_set()
    assert CommandService(db).owned(request.id, actor).status == "PLANNING_FAILED"
    assert db.scalar(select(func.count()).select_from(Task)) == 0


def test_stringified_candidate_secrets_are_sanitized():
    import json

    from app.agents.command_agent import safe_candidate

    candidate = {"items": json.dumps([{"arguments": {"password": "hidden", "task_name": "QA"}}])}
    assert safe_candidate(candidate) == {"items": [{"arguments": {"task_name": "QA"}}]}


def test_auxiliary_query_soft_source_mapping_does_not_block_plan():
    source = (
        "在项目 PRJ-1001 中创建任务：\n"
        "1. 方案评审 —— 负责人 测试甲 —— 协作 测试乙 —— 工期 5 天\n"
        "2. 实施推进 —— 负责人 测试乙"
    )
    items = [
        {
            "item_id": "owners",
            "tool": "batch_find_users",
            # Scattered summary that is not a contiguous quote of the source.
            "source_text": "核对负责人：测试甲、测试乙",
            "arguments": {"names": ["测试甲", "测试乙"]},
        },
        {
            "item_id": "batch",
            "tool": "batch_create_tasks",
            "source_text": source,
            "depends_on": ["owners"],
            "arguments": {
                "project_code": "PRJ-1001",
                "items": [
                    {
                        "client_item_id": "t1",
                        "task_name": "方案评审",
                        "owner_name": "测试甲",
                        "collaborator_names": ["测试乙"],
                        "planned_duration_days": 5,
                    },
                    {
                        "client_item_id": "t2",
                        "task_name": "实施推进",
                        "owner_name": "测试乙",
                    },
                ],
            },
        },
    ]
    spans = validate_coverage(CommandPlanInput(items=items), source)
    # Soft unresolved (0,0) or a located name fragment — either must not block the plan.
    assert spans[0][1] >= spans[0][0]
    assert spans[1][1] > spans[1][0]


def test_write_step_still_requires_authorizing_source_quote():
    source = "创建任务：方案评审 —— 测试甲"
    items = [
        {
            "item_id": "batch",
            "tool": "batch_create_tasks",
            "source_text": "完全无关的授权文本",
            "arguments": {
                "project_code": "PRJ-1001",
                "items": [
                    {
                        "client_item_id": "t1",
                        "task_name": "方案评审",
                        "owner_name": "测试甲",
                    }
                ],
            },
        }
    ]
    with pytest.raises(ValueError, match="原文映射不匹配"):
        validate_coverage(CommandPlanInput(items=items), source)


def test_format_execution_distinguishes_steps_and_created_tasks():
    summary = format_execution(
        {
            "expected_count": 2,
            "succeeded": 2,
            "business_succeeded": 1,
            "created_task_count": 3,
            "status": "COMPLETED",
            "items": [
                {
                    "item_id": "owners",
                    "tool": "batch_find_users",
                    "source_text": "核对人员",
                    "state": "SUCCEEDED",
                    "result": {},
                },
                {
                    "item_id": "batch",
                    "tool": "batch_create_tasks",
                    "source_text": "创建任务",
                    "state": "SUCCEEDED",
                    "result": {"data": {"created_task_count": 3}},
                },
            ],
        }
    )
    assert "执行步骤" in summary
    assert "业务写入步骤成功 1" in summary
    assert "实际创建任务 3 个" in summary


def test_format_execution_softens_source_mapping_errors_when_unplanned():
    write_summary = format_execution(
        {
            "unplanned": True,
            "error": "tasks_med_chem 的原文映射不匹配（写入步骤必须能对上用户授权原文）",
            "items": [],
        }
    )
    assert "原文映射" not in write_summary
    assert "再次确认创建" in write_summary

    aux_summary = format_execution(
        {
            "unplanned": True,
            "error": "owners 的原文映射不匹配",
            "items": [],
        }
    )
    assert "原文映射" not in aux_summary
    assert "任务尚未创建" in aux_summary
    assert "无需为了内部字段改写清单" in aux_summary
