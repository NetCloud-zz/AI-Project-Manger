"""Reset a user's password from the environment or an interactive prompt.

Usage (inside backend container / venv)::

    SEED_ADMIN_PASSWORD='...' python -m app.scripts.set_user_password --username admin

Never pass passwords on the argv when shell history is retained; prefer env vars.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.user import User
from app.services.user import UserService

logger = get_logger(__name__)

_PUBLIC = frozenset(
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


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Reset a local user password")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--password-env",
        default="",
        help="Environment variable holding the new password (preferred)",
    )
    args = parser.parse_args(argv)

    password = ""
    if args.password_env:
        password = (os.environ.get(args.password_env) or "").strip()
        if not password:
            print(f"Environment variable {args.password_env} is empty", file=sys.stderr)
            return 2
    else:
        # Fallbacks used by ops scripts; avoid argv.
        for key in ("NEW_PASSWORD", "SEED_ADMIN_PASSWORD"):
            password = (os.environ.get(key) or "").strip()
            if password:
                break
        if not password and sys.stdin.isatty():
            password = getpass.getpass("New password: ").strip()

    if not password or len(password) < 10:
        print("Password must be at least 10 characters", file=sys.stderr)
        return 2
    if password in _PUBLIC:
        print("Refusing documented public seed password", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            print(f"User {args.username!r} not found", file=sys.stderr)
            return 1
        UserService(db).reset_password(user, password, actor_id=None)
        db.commit()
        logger.info("password.reset_ok", username=args.username, user_id=user.id)
        print(f"Password updated for {args.username}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
