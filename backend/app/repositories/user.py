"""User data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self.db.scalar(select(User).where(User.username == username))

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email))

    def get_by_wechat_user_id(self, wechat_user_id: str) -> User | None:
        return self.db.scalar(select(User).where(User.wechat_user_id == wechat_user_id))

    def get_by_oa_admin_id(self, oa_admin_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.oa_admin_id == oa_admin_id))

    def list_all(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.id)).all())

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def save(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user
