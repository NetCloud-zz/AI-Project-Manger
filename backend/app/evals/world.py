"""Disposable, desensitized data world for agent-mode evaluation.

Agent-mode cases run either in in-memory SQLite or in a throwaway PostgreSQL
schema created on ``DATABASE_URL`` and dropped afterwards. Nothing touches the
application's own tables.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register every table on Base.metadata
from app.core.database import Base
from app.models.action_item import ActionItem
from app.models.issue import Issue, IssueSeverity, IssueStatus
from app.models.plan_draft import PlanDraft
from app.models.planning import Milestone
from app.models.progress_update import ProgressUpdate
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole

COUNTED = {
    "task": Task,
    "project": Project,
    "issue": Issue,
    "action_item": ActionItem,
    "milestone": Milestone,
    "progress_update": ProgressUpdate,
    "plan_draft": PlanDraft,
}


@dataclass(frozen=True, slots=True)
class World:
    users: dict[str, User]
    project: Project
    values: dict[str, str]

    def actor(self, role: str) -> User:
        return self.users.get(role) or self.users["PROJECT_OWNER"]


@contextmanager
def disposable_session(database_url: str | None) -> Iterator[Session]:
    """SQLite in memory when ``database_url`` is None, else a throwaway PG schema."""
    if database_url is None:
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(engine)
        try:
            with Session(engine, expire_on_commit=False) as session:
                yield session
        finally:
            engine.dispose()
        return

    schema = "eval_assistant_" + uuid4().hex[:16]
    root = create_engine(database_url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        database_url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=8
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


def seed_world(db: Session, *, run_tag: str) -> World:
    today = date.today()
    people = {
        "ADMIN": User(name="示例管理员", username="eval_admin", role=UserRole.ADMIN),
        "PROJECT_OWNER": User(
            name="示例负责人", username="eval_owner", role=UserRole.PROJECT_OWNER
        ),
        "MEMBER": User(name="测试甲", username="eval_member_a", role=UserRole.MEMBER),
        "MEMBER_B": User(name="测试乙", username="eval_member_b", role=UserRole.MEMBER),
        "EXECUTIVE": User(name="示例高管", username="eval_exec", role=UserRole.EXECUTIVE),
    }
    for user in people.values():
        user.password_hash = "unused"
    db.add_all(people.values())
    db.flush()

    owner, member_a, member_b = people["PROJECT_OWNER"], people["MEMBER"], people["MEMBER_B"]
    project = Project(project_code="PRJ-1001", project_name="示例交付项目", owner_id=owner.id)
    other = Project(
        project_code="PRJ-1002", project_name="示例运营项目", owner_id=people["ADMIN"].id
    )
    db.add_all([project, other])
    db.flush()
    db.add_all(
        [
            Task(
                project_id=project.id,
                task_name="需求评审",
                owner_id=member_a.id,
                status=TaskStatus.IN_PROGRESS,
                progress_percent=40,
                start_date=today - timedelta(days=5),
                due_date=today + timedelta(days=3),
                work_stream="准备阶段",
            ),
            Task(
                project_id=project.id,
                task_name="接口联调",
                owner_id=member_b.id,
                status=TaskStatus.TODO,
                due_date=today + timedelta(days=10),
                work_stream="实施阶段",
            ),
            Task(
                project_id=project.id,
                task_name="上线检查",
                owner_id=member_a.id,
                status=TaskStatus.TODO,
                due_date=today - timedelta(days=2),
                work_stream="实施阶段",
            ),
            Task(
                project_id=other.id,
                task_name="活动复盘",
                owner_id=people["ADMIN"].id,
                status=TaskStatus.TODO,
            ),
            Issue(
                project_id=project.id,
                reported_by=owner.id,
                title="外部交付物延迟",
                description="外部交付物尚未到位，影响评审排期。",
                severity=IssueSeverity.HIGH,
                status=IssueStatus.OPEN,
            ),
        ]
    )
    db.commit()
    values = {
        "project_code": project.project_code,
        "project_id": str(project.id),
        "n1": f"评测任务A-{run_tag}",
        "n2": f"评测任务B-{run_tag}",
        "n3": f"评测任务C-{run_tag}",
    }
    return World(users=people, project=project, values=values)


def snapshot_counts(db: Session) -> dict[str, int]:
    db.expire_all()
    return {
        name: int(db.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in COUNTED.items()
    }
