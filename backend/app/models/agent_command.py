"""Durable command plans; item results are committed with database side effects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base
from app.models.base import TimestampMixin

_JSON = JSON().with_variant(JSONB(), "postgresql")


class AgentCommandPlan(TimestampMixin, Base):
    __tablename__ = "agent_command_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("agent_requests.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    policy: Mapped[str] = mapped_column(String(20), default="independent", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PLANNING", nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    planning_details: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentCommandItem(TimestampMixin, Base):
    __tablename__ = "agent_command_items"
    __table_args__ = (UniqueConstraint("plan_id", "item_id", name="uq_command_plan_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("agent_command_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_start: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end: Mapped[int] = mapped_column(Integer, nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    depends_on: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="PENDING", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
