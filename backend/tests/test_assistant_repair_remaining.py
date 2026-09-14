"""Remaining repair coverage: milestones, multi-fragment evidence, plan switch."""

from __future__ import annotations

from datetime import date

import pytest
import yaml
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.core.config import Settings
from app.models.planning import Milestone
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas.agent_command import CommandPlanInput, locate_auxiliary_evidence, validate_coverage
from app.services.management_write import ManagementWriteService
from pathlib import Path


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
        username="milestone_owner",
        password_hash="unused",
        role=UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    return user


def test_create_milestone_persists_project_gate(db, actor):
    project = Project(project_code="PRJ-1001", project_name="演示", owner_id=actor.id)
    db.add(project)
    db.commit()
    result = ManagementWriteService(db).create_milestone(
        actor,
        {
            "project_code": "PRJ-1001",
            "name": "阶段门禁-M1",
            "target_date": "2026-10-31",
            "owner_name": "测试甲",
        },
    )
    assert result["ok"] is True
    row = db.scalar(select(Milestone).where(Milestone.name == "阶段门禁-M1"))
    assert row is not None
    assert row.project_id == project.id
    assert row.target_date == date(2026, 10, 31)
    assert row.owner_id == actor.id
    assert db.scalar(select(func.count()).select_from(Milestone)) == 1


def test_auxiliary_multi_fragment_evidence_locates_name_piece():
    source = "创建任务：方案评审 —— 测试甲；实施推进 —— 测试乙"
    span = locate_auxiliary_evidence(source, "核对负责人：测试甲、测试乙")
    assert span != (0, 0)
    assert source[span[0] : span[1]] in {"测试甲", "测试乙"}


def test_auxiliary_soft_fallback_still_allows_plan():
    source = "在项目 PRJ-1001 创建任务 A"
    items = [
        {
            "item_id": "owners",
            "tool": "batch_find_users",
            "source_text": "完全无关的摘要词",
            "arguments": {"names": ["测试甲"]},
        },
        {
            "item_id": "task",
            "tool": "create_task",
            "source_text": source,
            "depends_on": ["owners"],
            "arguments": {"project_code": "PRJ-1001", "task_name": "A"},
        },
    ]
    spans = validate_coverage(CommandPlanInput(items=items), source)
    assert spans[0] == (0, 0)


def test_command_plan_feature_flag_defaults_enabled():
    settings = Settings(_env_file=None)
    assert settings.COMMAND_PLAN_ENABLED is True


def test_eval_fixture_24x1_counts():
    path = Path(__file__).resolve().parents[1] / "evals" / "assistant_repair_24x1.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["expect"]["task_count"] == 24
    assert data["expect"]["milestone_count"] == 1
    assert data["expect"]["group_sizes"] == [7, 6, 5, 6]
    tasks = [task for group in data["groups"] for task in group["tasks"]]
    assert len(tasks) == 24
    assert data["milestone"]["name"]
