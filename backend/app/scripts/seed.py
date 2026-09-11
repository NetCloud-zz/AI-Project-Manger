"""Database seed entrypoint.

Usage:
    python -m app.scripts.seed

Creates default development users and a generic demo project (PRJ-1001).
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

# Documented demo passwords from older releases — never reuse on shared stacks.
PUBLIC_SEED_PASSWORDS = frozenset(
    {
        "Admin@12345",
        "Executive@12345",
        "Owner@12345",
        "Owner2@12345",
        "Lisi@12345",
        "Member@12345",
        "Member2@12345",
        "Member3@12345",
        "Member4@12345",
    }
)


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
        "department": "Engineering",
    },
    {
        "name": "项目负责人乙",
        "username": "owner2",
        "password_env": "SEED_OWNER2_PASSWORD",
        "default_password": "Owner2@12345",
        "role": UserRole.PROJECT_OWNER,
        "department": "Product",
    },
    {
        "name": "李四",
        "username": "lisi",
        "password_env": "SEED_LISI_PASSWORD",
        "default_password": "Lisi@12345",
        "role": UserRole.MEMBER,
        "department": "Engineering",
    },
    {
        "name": "成员甲",
        "username": "member",
        "password_env": "SEED_MEMBER_PASSWORD",
        "default_password": "Member@12345",
        "role": UserRole.MEMBER,
        "department": "Engineering",
    },
    {
        "name": "成员乙",
        "username": "member2",
        "password_env": "SEED_MEMBER2_PASSWORD",
        "default_password": "Member2@12345",
        "role": UserRole.MEMBER,
        "department": "Product",
    },
    {
        "name": "成员丙",
        "username": "member3",
        "password_env": "SEED_MEMBER3_PASSWORD",
        "default_password": "Member3@12345",
        "role": UserRole.MEMBER,
        "department": "Operations",
    },
    {
        "name": "成员丁",
        "username": "member4",
        "password_env": "SEED_MEMBER4_PASSWORD",
        "default_password": "Member4@12345",
        "role": UserRole.MEMBER,
        "department": "Operations",
    },
]

DEMO_PROJECT: dict[str, Any] = {
    "project_code": "PRJ-1001",
    "project_name": "示例产品上线",
    "goal": "2026-12-20 前完成首版上线与验收",
    "target_date": date(2026, 12, 20),
    "tasks": [
        {
            "task_name": "完成需求澄清与范围确认",
            "work_stream": "规划",
            "owner_username": "member",
            "start_date": date(2026, 8, 25),
            "due_date": date(2026, 9, 15),
            "progress_percent": 60,
            "status": TaskStatus.IN_PROGRESS,
        },
        {
            "task_name": "完成核心功能开发",
            "work_stream": "开发",
            "owner_username": "lisi",
            "start_date": date(2026, 8, 20),
            "due_date": date(2026, 9, 8),
            "progress_percent": 40,
            "status": TaskStatus.IN_PROGRESS,
        },
        {
            "task_name": "完成联调与测试",
            "work_stream": "测试",
            "owner_username": "member2",
            "start_date": date(2026, 9, 16),
            "due_date": date(2026, 10, 1),
            "progress_percent": 0,
            "status": TaskStatus.TODO,
        },
        {
            "task_name": "完成上线与验收复盘",
            "work_stream": "上线",
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


def _resolve_seed_password(spec: UserSeedSpec) -> str:
    settings = get_settings()
    env_name = spec["password_env"]
    from_env = (os.environ.get(env_name) or "").strip()
    allow_public = settings.ENVIRONMENT == "local" and settings.ALLOW_PUBLIC_SEED_PASSWORDS

    if from_env:
        password = from_env
    elif allow_public:
        password = spec["default_password"]
        logger.warning(
            "seed.using_public_default_password",
            username=spec["username"],
            env=env_name,
        )
    else:
        raise SystemExit(
            f"Refusing to seed user {spec['username']!r} without {env_name}. "
            "Set a strong password in the environment, or for a throwaway local "
            "sandbox only set ALLOW_PUBLIC_SEED_PASSWORDS=true."
        )

    if password in PUBLIC_SEED_PASSWORDS and not allow_public:
        raise SystemExit(
            f"Refusing public seed password for {spec['username']!r}. "
            f"Choose a unique value for {env_name}."
        )
    if len(password) < 10:
        raise SystemExit(f"{env_name} must be at least 10 characters")
    return password


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

        password = _resolve_seed_password(spec)
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
    project_code = str(DEMO_PROJECT["project_code"])
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
        project_name=str(DEMO_PROJECT["project_name"]),
        goal=str(DEMO_PROJECT["goal"]),
        owner_id=owner.id,
        target_date=DEMO_PROJECT["target_date"],
        status=ProjectStatus.ACTIVE,
        risk_level=ProjectRiskLevel.NORMAL,
    )
    db.add(project)
    db.flush()

    task_specs: list[TaskSeedSpec] = DEMO_PROJECT["tasks"]
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
    for source_index, target_index in DEMO_PROJECT["links"]:
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
