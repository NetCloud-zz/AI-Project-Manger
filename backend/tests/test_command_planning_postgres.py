"""Opt-in acceptance in disposable PostgreSQL schemas only."""

from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base
from app.services.management_write import ManagementWriteService
from test_batch_owner_refs import (
    test_ambiguous_owner_blocks_whole_project_creation as test_pg_ambiguous_owners,  # noqa: F401
)
from test_batch_owner_refs import (
    test_batch_owner_create_and_resume_preserve_both_owners as test_pg_batch_owner_refs,  # noqa: F401
)
from test_command_planning_repair import (
    Gateway,
    collect,
    setup,
)
from test_command_planning_repair import (
    actor as actor,
)
from test_command_planning_repair import (
    test_25_rows_wrong_declared_count_does_not_fail as test_pg_wrong_count,  # noqa: F401
)
from test_command_planning_repair import (
    test_budget_resume_skips_successful_items as test_budget_resume_skips_successful_items,
)
from test_command_planning_repair import (
    test_missing_reference_is_recorded_not_raised as test_missing_reference_is_recorded_not_raised,
)
from test_command_planning_repair import (
    test_validation_failure_does_not_leave_atomic_partial_writes as test_pg_atomic_failure,  # noqa: F401
)

pytestmark = pytest.mark.skipif(
    os.getenv("COMMAND_PG_TESTS") != "1", reason="Opt-in isolated PostgreSQL acceptance"
)


@pytest.fixture
def db():
    schema = "qa_command_repair_" + uuid4().hex
    root = create_engine(get_settings().DATABASE_URL)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        get_settings().DATABASE_URL,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=8,
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()
        with root.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def test_migration_roundtrip(db):
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/20260911_1000_f8a9b0c1d2e3_planning_diagnostics.py"
    )
    spec = importlib.util.spec_from_file_location("planning_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with (
        db.get_bind().begin() as connection,
        Operations.context(MigrationContext.configure(connection)),
    ):
        module.downgrade()
        assert "planning_details" not in {
            c["name"] for c in inspect(connection).get_columns("agent_command_plans")
        }
        module.upgrade()
        assert "planning_details" in {
            c["name"] for c in inspect(connection).get_columns("agent_command_plans")
        }


@pytest.mark.asyncio
async def test_four_independent_creates_overlap(db, actor, monkeypatch):
    request, source, items = setup(db, actor, 4)
    barrier = threading.Barrier(4, timeout=10)
    connections = set()
    original = ManagementWriteService.create_task

    def overlap(self, actor, args):
        connections.add(self.db.scalar(text("SELECT pg_backend_pid()")))
        barrier.wait()
        return original(self, actor, args)

    monkeypatch.setattr(ManagementWriteService, "create_task", overlap)
    events = await collect(db, actor, request, source, Gateway({"items": items}))
    assert [e.data for e in events if e.event == "card"][-1]["succeeded"] == 4
    assert len(connections) == 4


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("COMMAND_REAL_MODEL") != "1", reason="Opt-in real model acceptance")
async def test_real_model_numbered_25_tasks(db, actor):
    from app.agents.command_agent import command_stream
    from app.llm.gateway import create_llm_gateway
    from app.services.agent_commands import CommandService

    request, source, _ = setup(db, actor, 25)
    source = (
        "请在已有项目 PRJ-1001 中"
        + source
        + "\n所有任务负责人为登录用户名 qa_owner，日期暂不设置。每个编号各创建一个任务，不创建其他任务。"
    )
    settings = get_settings()
    gateway = create_llm_gateway(settings)
    assert gateway.configured, "Real model not configured"
    events = [e async for e in command_stream(db, gateway, settings, source, actor, request.id)]
    plan = CommandService(db).owned(request.id, actor)
    snapshot = [e.data for e in events if e.event == "card"][-1]
    assert snapshot["succeeded"] == 25, {
        "status": snapshot["status"],
        "details": plan.planning_details,
        "items": snapshot["items"],
    }


@pytest.mark.asyncio
async def test_http_cancellation_settles_writes(db, actor, monkeypatch):
    import asyncio

    from sqlalchemy import func, select

    from app.models.task import Task
    from app.services.agent_commands import CommandService

    request, source, items = setup(db, actor, 4)
    entered, release = threading.Event(), threading.Event()
    original = ManagementWriteService.create_task

    def paused(self, actor, args):
        entered.set()
        assert release.wait(10)
        return original(self, actor, args)

    monkeypatch.setattr(ManagementWriteService, "create_task", paused)
    running = asyncio.create_task(collect(db, actor, request, source, Gateway({"items": items})))
    assert await asyncio.to_thread(entered.wait, 10)
    running.cancel()
    await asyncio.sleep(0)
    assert not running.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert db.scalar(select(func.count()).select_from(Task)) == 4
    service = CommandService(db)
    snapshot = service.snapshot(service.owned(request.id, actor))
    assert snapshot["status"] == "COMPLETED"
    assert snapshot["succeeded"] == 4


@pytest.mark.asyncio
async def test_external_stop_rolls_back_atomic_batch(db, actor, monkeypatch):
    from sqlalchemy import func, select

    from app.agents.management_tools import ManagementToolExecutor
    from app.models.agent_request import AgentRequest
    from app.models.task import Task

    request, source, items = setup(db, actor)
    source += "\n要么全部成功，否则全部回滚"
    original = ManagementToolExecutor.execute_result

    def stop_after_write(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        with Session(db.get_bind()) as other:
            other.get(AgentRequest, request.id).cancel_requested = True
            other.commit()
        return result

    monkeypatch.setattr(ManagementToolExecutor, "execute_result", stop_after_write)
    await collect(db, actor, request, source, Gateway({"items": items, "policy": "atomic"}))
    assert db.scalar(select(func.count()).select_from(Task)) == 0
