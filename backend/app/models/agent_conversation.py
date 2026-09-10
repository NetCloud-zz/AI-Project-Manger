"""Agent conversation and message ORM models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

# SQLite tests use JSON; Postgres prefers JSONB.
_JSON = JSON().with_variant(JSONB(), "postgresql")


class ConversationStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class MessageStatus(enum.StrEnum):
    PENDING = "PENDING"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    INTERRUPTED = "INTERRUPTED"


class AgentConversation(TimestampMixin, Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        Index("ix_agent_conversations_user_last_message", "user_id", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="agent_conversation_status", native_enum=False, length=16),
        nullable=False,
        default=ConversationStatus.ACTIVE,
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    # Reserved for PHASE B rolling summary — nullable now so we avoid a second migration.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Last message id covered by the rolling summary (OPT-08).
    summary_through_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    project = relationship("Project", foreign_keys=[project_id])
    messages = relationship(
        "AgentMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AgentMessage.id",
    )


class AgentMessage(Base):
    """Chat turn. Uses created_at only — no updated_at (append-oriented)."""

    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_agent_messages_parent_user", "parent_user_message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="agent_message_role", native_enum=False, length=16),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="agent_message_status", native_enum=False, length=20),
        nullable=False,
        default=MessageStatus.COMPLETED,
    )
    # Tool name list / brief results — never chain-of-thought.
    tool_calls: Mapped[list[Any] | None] = mapped_column(_JSON, nullable=True)
    tool_results: Mapped[list[Any] | None] = mapped_column(_JSON, nullable=True)
    # Structured references (plan draft / change proposal / notifications) the UI
    # renders as actionable cards. Authorization still happens server-side.
    cards: Mapped[list[Any] | None] = mapped_column(_JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: ASSISTANT → owning USER turn (OPT-04). Null only for legacy / unknown.
    parent_user_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: ASSISTANT → previous answer this version was regenerated from.
    regenerated_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: 1-based version within the same parent_user_message_id.
    answer_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: USER → currently selected ASSISTANT answer id for display / context.
    selected_answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: NORMAL when association is known; LEGACY when historical binding is unknown.
    association_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="NORMAL"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation = relationship("AgentConversation", back_populates="messages")
