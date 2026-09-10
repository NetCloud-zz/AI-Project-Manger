"""Database seed entrypoint.

Usage:
    python -m app.scripts.seed

Creates default development users and the OPS-2071 demo project (Phase 12).
Production deployments must override all default passwords via SEED_* env vars.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.project import Project, ProjectRiskLevel, ProjectStatus
from app.models.task import Task, TaskLink, TaskLinkType, TaskStatus
from app.models.user import User, UserRole
from app.schemas.user import UserCreate
from app.services.user import UserService

logger = get_logger(__name__)


class UserSeedSpec(TypedDict):
    name: str
    username: str
    password_env: str
    default_password: str
    role: UserRole
    department: str


class TaskSeedSpec(TypedDict):
    task_name: str
    work_stream: str
    owner_username: str
    start_date: date
    due_date: date
    progress_percent: int
    status: TaskStatus


DEFAULT_USERS: list[UserSeedSpec] = [
    {
        "name": "系统管理员",
        "username": "admin",
        "password_env": "SEED_ADMIN_PASSWORD",
        "default_password": "Admin@12345",
        "role": UserRole.ADMIN,
        "department": "IT",
    },
    {
        "name": "总经理",
        "username": "executive",
        "password_env": "SEED_EXECUTIVE_PASSWORD",
        "default_password": "Executive@12345",
        "role": UserRole.EXECUTIVE,
        "department": "Management",
    },
    {
        "name": "项目负责人甲",
        "username": "owner",
        "password_env": "SEED_OWNER_PASSWORD",
        "default_password": "Owner@12345",
        "role": UserRole.PROJECT_OWNER,
        "department": "R&D",
    },
    {
        "name": "项目负责人乙",
        "username": "owner2",
        "password_env": "SEED_OWNER2_PASSWORD",
        "default_password": "Owner2@12345",
        "role": UserRole.PROJECT_OWNER,
        "department": "R&D",
    },
    {
        "name": "李四",
        "username": "lisi",
        "password_env": "SEED_LISI_PASSWORD",
        "default_password": "Lisi@12345",
        "role": UserRole.MEMBER,
        "department": "R&D",
    },
    {
        "name": "研发成员甲",
        "username": "member",
        "password_env": "SEED_MEMBER_PASSWORD",
        "default_password": "Member@12345",
        "role": UserRole.MEMBER,
        "department": "R&D",
    },
    {
        "name": "研发成员乙",
        "username": "member2",
        "password_env": "SEED_MEMBER2_PASSWORD",
        "default_password": "Member2@12345",
        "role": UserRole.MEMBER,
        "department": "R&D",
    },
    {
        "name": "研发成员丙",
        "username": "member3",
        "password_env": "SEED_MEMBER3_PASSWORD",
        "default_password": "Member3@12345",
        "role": UserRole.MEMBER,
        "department": "R&D",
    },
    {
        "name": "研发成员丁",
        "username": "member4",
        "password_env": "SEED_MEMBER4_PASSWORD",
        "default_password": "Member4@12345",
        "role": UserRole.MEMBER,
        "department": "R&D",
    },
]

OPS_2071: dict[str, Any] = {
    "project_code": "OPS-2071",
    "project_name": "PCC Candidate 筛选",
    "goal": "2026-12-20 前完成 PCC Candidate 确定",
    "target_date": date(2026, 12, 20),
    "tasks": [
        {
            "task_name": "完成第二轮体外活性实验",
            "work_stream": "体外筛选",
            "owner_username": "member",
            "start_date": date(2026, 8, 25),
            "due_date": date(2026, 9, 15),
            "progress_percent": 60,
            "status": TaskStatus.IN_PROGRESS,
        },
        {
            "task_name": "完成 PK 实验",
            "work_stream": "药代评价",
            "owner_username": "lisi",
            "start_date": date(2026, 8, 20),
            "due_date": date(2026, 9, 8),
            "progress_percent": 40,
            "status": TaskStatus.IN_PROGRESS,
        },
        {
            "task_name": "完成初步安全性评估",
            "work_stream": "安全性评价",
            "owner_username": "member2",
            "start_date": date(2026, 9, 16),
            "due_date": date(2026, 10, 1),
            "progress_percent": 0,
            "status": TaskStatus.TODO,
        },
        {
            "task_name": "完成候选化合物综合评价",
            "work_stream": "候选决策",
            "owner_username": "member3",
            "start_date": date(2026, 10, 2),
            "due_date": date(2026, 11, 15),
            "progress_percent": 0,
            "status": TaskStatus.TODO,
        },
    ],
    # Index pairs into "tasks" above: predecessor -> successor.
    "links": [(1, 0), (0, 2), (2, 3)],
}


def seed_users(db: Session) -> dict[str, User]:
    service = UserService(db)
    users_by_username: dict[str, User] = {}
    created = 0
    for spec in DEFAULT_USERS:
        username = spec["username"]
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            logger.info("seed.user_exists", username=username)
            users_by_username[username] = existing
            continue

        password = os.environ.get(spec["password_env"], spec["default_password"])
        user = service.create_user(
            UserCreate(
                name=spec["name"],
                username=username,
                password=password,
                role=spec["role"],
                department=spec["department"],
                email=f"{username}@example.com",
            ),
            actor_id=None,
        )
        users_by_username[username] = user
        created += 1
        logger.info(
            "seed.user_created",
            username=user.username,
            role=user.role.value,
            status=user.status.value,
        )
    logger.info("seed.users_complete", created=created, total=len(users_by_username))
    return users_by_username


def seed_demo_project(db: Session, users_by_username: dict[str, User]) -> None:
    project_code = str(OPS_2071["project_code"])
    existing = db.scalar(select(Project).where(Project.project_code == project_code))
    if existing:
        logger.info("seed.project_exists", project_code=project_code)
        return

    owner = users_by_username.get("owner")
    if owner is None:
        logger.warning("seed.demo_project_skipped", reason="owner user missing")
        return

    project = Project(
        project_code=project_code,
        project_name=str(OPS_2071["project_name"]),
        goal=str(OPS_2071["goal"]),
        owner_id=owner.id,
        target_date=OPS_2071["target_date"],
        status=ProjectStatus.ACTIVE,
        risk_level=ProjectRiskLevel.NORMAL,
    )
    db.add(project)
    db.flush()

    task_specs: list[TaskSeedSpec] = OPS_2071["tasks"]
    tasks_by_index: dict[int, Task] = {}
    for index, task_spec in enumerate(task_specs):
        task_owner = users_by_username.get(task_spec["owner_username"])
        if task_owner is None:
            logger.warning(
                "seed.task_skipped",
                task_name=task_spec["task_name"],
                owner_username=task_spec["owner_username"],
            )
            continue
        task = Task(
            project_id=project.id,
            task_name=task_spec["task_name"],
            work_stream=task_spec["work_stream"],
            owner_id=task_owner.id,
            start_date=task_spec["start_date"],
            due_date=task_spec["due_date"],
            progress_percent=task_spec["progress_percent"],
            status=task_spec["status"],
        )
        db.add(task)
        tasks_by_index[index] = task
    db.flush()

    links_created = 0
    for source_index, target_index in OPS_2071["links"]:
        source = tasks_by_index.get(source_index)
        target = tasks_by_index.get(target_index)
        if source is None or target is None:
            continue
        db.add(
            TaskLink(
                project_id=project.id,
                source_id=source.id,
                target_id=target.id,
                link_type=TaskLinkType.FINISH_TO_START,
            )
        )
        links_created += 1

    logger.info(
        "seed.demo_project_created",
        project_code=project_code,
        tasks=len(tasks_by_index),
        links=links_created,
    )


def seed_all() -> None:
    settings = get_settings()
    configure_logging(settings)

    with SessionLocal() as db:
        users = seed_users(db)
        seed_demo_project(db, users)
        db.commit()
        logger.info("seed.complete")


def main() -> int:
    try:
        seed_all()
    except Exception:
        logger.exception("seed.failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
