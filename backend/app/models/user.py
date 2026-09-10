"""User ORM model."""

from __future__ import annotations

import enum

from sqlalchemy import Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class UserRole(enum.StrEnum):
    ADMIN = "ADMIN"
    EXECUTIVE = "EXECUTIVE"
    PROJECT_OWNER = "PROJECT_OWNER"
    MEMBER = "MEMBER"


class UserStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("oa_admin_id", name="uq_users_oa_admin_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wechat_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    oa_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=32),
        nullable=False,
        default=UserRole.MEMBER,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=False, length=16),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE
