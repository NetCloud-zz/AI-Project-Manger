"""ProgressUpdate ORM model."""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin
from app.models.task import TaskAiStatus


class ProgressUpdate(TimestampMixin, Base):
    __tablename__ = "progress_updates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    # AI fields — only worker may update; raw_content is immutable.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_status: Mapped[TaskAiStatus | None] = mapped_column(
        Enum(TaskAiStatus, name="progress_ai_status", native_enum=False, length=16),
        nullable=True,
    )
    risk_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_analysis_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    task = relationship("Task", back_populates="progress_updates")
    user = relationship("User", foreign_keys=[user_id])
