"""Agent user memory ORM model."""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class MemoryScope(enum.StrEnum):
    USER = "USER"
    PROJECT = "PROJECT"


class MemoryType(enum.StrEnum):
    PREFERENCE = "PREFERENCE"
    INSTRUCTION = "INSTRUCTION"
    PINNED_CONTEXT = "PINNED_CONTEXT"


class AgentMemory(TimestampMixin, Base):
    __tablename__ = "agent_memories"
    __table_args__ = (
        Index("ix_agent_memories_user_active", "user_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    scope: Mapped[MemoryScope] = mapped_column(
        Enum(MemoryScope, name="agent_memory_scope", native_enum=False, length=16),
        nullable=False,
        default=MemoryScope.USER,
    )
    memory_type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="agent_memory_type", native_enum=False, length=32),
        nullable=False,
        default=MemoryType.PREFERENCE,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
