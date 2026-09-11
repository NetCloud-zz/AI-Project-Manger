"""Idempotent batch operations for structured Agent intents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

_JSON = JSON().with_variant(JSONB(), "postgresql")


class AgentBatchOperation(TimestampMixin, Base):
    __tablename__ = "agent_batch_operations"
    __table_args__ = (UniqueConstraint("operation_id", name="uq_agent_batch_operations_op"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    expected_count: Mapped[int] = mapped_column(nullable=False, default=0)
    details: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)


class AgentBatchItem(TimestampMixin, Base):
    __tablename__ = "agent_batch_items"
    __table_args__ = (
        UniqueConstraint("operation_id", "client_item_id", name="uq_agent_batch_item"),
        Index("ix_agent_batch_items_operation", "operation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    client_item_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
