"""Unified AI background run status ORM model."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIRunType(enum.StrEnum):
    PROGRESS_ANALYSIS = "PROGRESS_ANALYSIS"
    ISSUE_ADVICE = "ISSUE_ADVICE"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    CONVERSATION_SUMMARY = "CONVERSATION_SUMMARY"


class AIRunStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class AIRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        Index("ix_ai_runs_resource", "resource_type", "resource_id", "created_at"),
        Index("ix_ai_runs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_type: Mapped[AIRunType] = mapped_column(
        Enum(AIRunType, name="ai_run_type", native_enum=False, length=32),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AIRunStatus] = mapped_column(
        Enum(AIRunStatus, name="ai_run_status", native_enum=False, length=16),
        nullable=False,
        default=AIRunStatus.QUEUED,
        index=True,
    )
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
