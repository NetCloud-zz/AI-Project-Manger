"""Wipe all application business data (keep alembic_version).

Usage:
    python -m app.scripts.wipe_business_data --yes

Optionally recreate a single local ADMIN break-glass account:
    python -m app.scripts.wipe_business_data --yes --seed-admin

Does NOT touch OA MySQL.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.core.logging import configure_logging, get_logger
from app.models.user import UserRole
from app.schemas.user import UserCreate
from app.services.user import UserService

logger = get_logger(__name__)

# Order does not matter with TRUNCATE ... CASCADE; listed for readability.
# Keep alembic_version. Include every app table so orphans cannot survive
# after schema additions that lack a FK path into the older core set.
BUSINESS_TABLES = (
    "action_items",
    "advice_records",
    "agent_messages",
    "agent_memories",
    "agent_conversations",
    "ai_runs",
    "audit_logs",
    "branch_options",
    "branch_groups",
    "change_proposals",
    "daily_project_summaries",
    "issues",
    "milestones",
    "notification_events",
    "plan_drafts",
    "plan_versions",
    "progress_updates",
    "project_members",
    "project_owners",
    "risk_events",
    "task_groups",
    "task_links",
    "task_participants",
    "tasks",
    "work_calendars",
    "projects",
    "users",
)


def wipe_all() -> None:
    quoted = ", ".join(f'"{name}"' for name in BUSINESS_TABLES)
    sql = text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    with engine.begin() as conn:
        conn.execute(sql)
    logger.info("wipe.completed", tables=list(BUSINESS_TABLES))


def seed_breakglass_admin(*, password: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        service = UserService(db, settings)
        user = service.create_user(
            UserCreate(
                name="系统管理员",
                username="admin",
                password=password,
                role=UserRole.ADMIN,
                department="IT",
                email=None,
            )
        )
        db.commit()
        logger.info("wipe.seed_admin", user_id=user.id, username=user.username)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Wipe local business data (not OA)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation flag",
    )
    parser.add_argument(
        "--seed-admin",
        action="store_true",
        help="After wipe, create local admin/Admin@12345 (or SEED_ADMIN_PASSWORD)",
    )
    args = parser.parse_args(argv)

    if not args.yes:
        print("Refusing to wipe without --yes", file=sys.stderr)
        return 2

    wipe_all()

    if args.seed_admin:
        import os

        password = os.environ.get("SEED_ADMIN_PASSWORD") or "Admin@12345"
        seed_breakglass_admin(password=password)
        print("Break-glass admin: username=admin")
    else:
        print("Wipe done. No local users remain; use OA SSO or --seed-admin.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
