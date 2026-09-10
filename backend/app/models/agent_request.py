"""Agent request / operation records for OPT-03 idempotency."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

_JSON = JSON().with_variant(JSONB(), "postgresql")


class AgentRequestStatus(enum.StrEnum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    INTERRUPTED = "INTERRUPTED"


class AgentOperationStatus(enum.StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AgentRequest(TimestampMixin, Base):
    """One client send attempt within a conversation (request-layer idempotency)."""

    __tablename__ = "agent_requests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "conversation_id",
            "client_request_id",
            name="uq_agent_requests_user_conversation_client",
        ),
        Index("ix_agent_requests_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    client_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    content_preview: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[AgentRequestStatus] = mapped_column(
        Enum(AgentRequestStatus, name="agent_request_status", native_enum=False, length=20),
        nullable=False,
        default=AgentRequestStatus.ACCEPTED,
    )
    user_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    operations = relationship("AgentOperation", back_populates="request", cascade="all, delete-orphan")


class AgentOperation(Base):
    """One side-effecting tool action bound to an AgentRequest (operation-layer idempotency)."""

    __tablename__ = "agent_operations"
    __table_args__ = (
        UniqueConstraint("operation_id", name="uq_agent_operations_operation_id"),
        Index("ix_agent_operations_request", "request_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("agent_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    args_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentOperationStatus] = mapped_column(
        Enum(AgentOperationStatus, name="agent_operation_status", native_enum=False, length=16),
        nullable=False,
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    request = relationship("AgentRequest", back_populates="operations")
