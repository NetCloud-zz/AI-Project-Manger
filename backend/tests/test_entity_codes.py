"""Daily P/T business code allocation."""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services.business_clock import BusinessClock
from app.services.entity_codes import (
    allocate_project_code,
    allocate_task_codes,
    day_stem,
    is_blank_or_placeholder_code,
)
from app.services.project import ProjectService
from app.services.task import TaskService


class FixedClock(BusinessClock):
    def today(self) -> date:  # type: ignore[override]
        return date(2026, 9, 11)


def _db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False), engine


def test_placeholder_detection():
    assert is_blank_or_placeholder_code(None)
    assert is_blank_or_placeholder_code("  ")
    assert is_blank_or_placeholder_code("待定")
    assert is_blank_or_placeholder_code("自动")
    assert not is_blank_or_placeholder_code("PRJ-1001")


def test_allocate_sequential_codes_for_day():
    db, engine = _db()
    try:
        clock = FixedClock()
        assert allocate_project_code(db, clock=clock) == "P20260911-001"
        assert allocate_project_code(db, clock=clock) == "P20260911-002"
        assert allocate_task_codes(db, 3, clock=clock) == [
            "T20260911-001",
            "T20260911-002",
            "T20260911-003",
        ]
        assert day_stem("project", clock=clock) == "P20260911-"
    finally:
        db.close()
        engine.dispose()


def test_create_project_and_task_auto_codes():
    db, engine = _db()
    try:
        actor = User(
            name="负责人", username="owner", password_hash="x", role=UserRole.PROJECT_OWNER
        )
        db.add(actor)
        db.commit()
        project = ProjectService(db).create_project(
            ProjectCreate(project_name="演示项目", owner_id=actor.id, project_code=None),
            actor=actor,
        )
        assert project.project_code.startswith("P")
        assert "-" in project.project_code
        task = TaskService(db).create_task(
            project.id,
            TaskCreate(task_name="首个任务", owner_id=actor.id),
            actor=actor,
        )
        assert task.task_code and task.task_code.startswith("T")
        db.commit()
    finally:
        db.close()
        engine.dispose()
