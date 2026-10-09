"""P0 assistant repair: batch field capability and resource-id verification."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.planning import TaskParticipant
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.services.agent_batch import AgentBatchService


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
        username="batch_owner_a",
        password_hash="unused",
        role=UserRole.ADMIN,
    )
    peer = User(
        name="测试乙",
        username="batch_owner_b",
        password_hash="unused",
        role=UserRole.PROJECT_OWNER,
    )
    db.add_all([user, peer])
    db.commit()
    return user, peer


def test_batch_create_persists_collaborators_and_duration(db, actor):
    owner, peer = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-collab",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "t1",
                    "task_name": "方案评审",
                    "owner_name": "测试甲",
                    "collaborator_names": ["测试乙"],
                    "work_stream": "准备阶段",
                    "start_date": "2026-09-01",
                    "due_date": "2026-09-05",
                    "planned_duration_days": 5,
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["created_task_count"] == 1
    assert result["verification"]["status"] == "SUCCESS"
    task = db.scalar(select(Task).where(Task.task_name == "方案评审"))
    assert task is not None
    assert task.owner_id == owner.id
    assert task.planned_duration_days == 5
    assert task.work_stream == "准备阶段"
    assert task.start_date == date(2026, 9, 1)
    assert task.due_date == date(2026, 9, 5)
    participants = list(
        db.scalars(select(TaskParticipant).where(TaskParticipant.task_id == task.id))
    )
    assert {row.user_id for row in participants} == {peer.id}


def test_batch_create_rejects_unsupported_milestone_fields(db, actor):
    owner, _ = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-milestone",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "m1",
                    "task_name": "阶段里程碑",
                    "owner_name": "测试甲",
                    "is_milestone": True,
                }
            ],
        },
    )
    assert result["ok"] is False
    assert result["error_code"] == "VALIDATION_FAILED"
    assert any(item["error_code"] == "CAPABILITY_UNSUPPORTED" for item in result["items"])
    assert db.scalar(select(Task)) is None


def test_batch_create_rejects_unknown_fields(db, actor):
    owner, _ = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-unknown",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "t1",
                    "task_name": "方案评审",
                    "owner_name": "测试甲",
                    "secret_flag": "x",
                }
            ],
        },
    )
    assert result["ok"] is False
    assert any(item["error_code"] == "INVALID_ARGUMENTS" for item in result["items"])
    assert db.scalar(select(Task)) is None


def test_batch_create_accepts_tasks_alias_and_auto_client_id(db, actor):
    owner, peer = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-tasks-alias",
            "project_code": "PRJ-1001",
            "tasks": [
                {
                    "task_name": "需求澄清",
                    "owner_names": ["测试甲", "测试乙"],
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["created_task_count"] == 1
    task = db.scalar(select(Task).where(Task.task_name == "需求澄清"))
    assert task is not None
    assert task.owner_id == owner.id
    owners = list(
        db.scalars(
            select(TaskParticipant).where(
                TaskParticipant.task_id == task.id, TaskParticipant.role == "OWNER"
            )
        )
    )
    assert {row.user_id for row in owners} == {peer.id}


def test_batch_create_multi_owner_from_joined_owner_name(db, actor):
    owner, peer = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-multi-owner",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "t1",
                    "task_name": "联合推进",
                    "owner_name": "测试甲、测试乙",
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["verification"]["status"] == "SUCCESS"
    task = db.scalar(select(Task).where(Task.task_name == "联合推进"))
    assert task is not None
    assert task.owner_id == owner.id
    participants = list(
        db.scalars(select(TaskParticipant).where(TaskParticipant.task_id == task.id))
    )
    assert len(participants) == 1
    assert participants[0].user_id == peer.id
    assert participants[0].role == "OWNER"


def test_batch_create_keeps_explicit_collaborators(db, actor):
    owner, peer = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-owner-vs-collab",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "t1",
                    "task_name": "区分角色",
                    "owner_name": "测试甲",
                    "collaborator_names": ["测试乙"],
                }
            ],
        },
    )
    assert result["ok"] is True
    task = db.scalar(select(Task).where(Task.task_name == "区分角色"))
    assert task is not None
    assert task.owner_id == owner.id
    participants = list(
        db.scalars(select(TaskParticipant).where(TaskParticipant.task_id == task.id))
    )
    assert len(participants) == 1
    assert participants[0].role == "COLLABORATOR"
    assert participants[0].user_id == peer.id


def test_batch_create_accepts_title_alias_and_numeric_owner_names(db, actor):
    owner, peer = actor
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=owner.id)
    db.add(project)
    db.commit()

    result = AgentBatchService(db).batch_create_tasks(
        owner,
        {
            "operation_id": "op-p0-title-ref",
            "project_code": "PRJ-1001",
            "items": [
                {
                    "client_item_id": "t1",
                    "title": "引用负责人",
                    "owner_names": [owner.id, peer.id],
                }
            ],
        },
    )
    assert result["ok"] is True
    task = db.scalar(select(Task).where(Task.task_name == "引用负责人"))
    assert task is not None
    assert task.owner_id == owner.id
    owners = list(
        db.scalars(
            select(TaskParticipant).where(
                TaskParticipant.task_id == task.id, TaskParticipant.role == "OWNER"
            )
        )
    )
    assert {row.user_id for row in owners} == {peer.id}
