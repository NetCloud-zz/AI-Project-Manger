"""Task response includes equal owners beyond the primary owner_id."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.planning import TaskParticipant
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.services.task import TaskService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def test_to_response_lists_primary_and_owner_participants(db):
    primary = User(name="测试甲", username="a", password_hash="x", role=UserRole.ADMIN)
    peer = User(name="测试乙", username="b", password_hash="x", role=UserRole.PROJECT_OWNER)
    db.add_all([primary, peer])
    db.flush()
    project = Project(project_code="PRJ-1001", project_name="测试项目", owner_id=primary.id)
    db.add(project)
    db.flush()
    task = Task(
        project_id=project.id,
        task_name="联合任务",
        owner_id=primary.id,
        task_code="T20260914-001",
    )
    db.add(task)
    db.flush()
    db.add(TaskParticipant(task_id=task.id, user_id=peer.id, role="OWNER"))
    db.commit()

    loaded = TaskService(db).get_task(task.id)
    payload = TaskService(db).to_response(loaded)
    assert [owner.name for owner in payload.owners] == ["测试甲", "测试乙"]
    assert payload.owner is not None
    assert payload.owner.name == "测试甲"
