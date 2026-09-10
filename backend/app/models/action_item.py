"""Action item ORM model.

An action item answers "who does what by when". It always belongs to a project
and may optionally hang off a task or an open issue, which lets a problem be
followed by concrete owned actions without duplicating the issue itself.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class ActionItemStatus(enum.StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ActionItemPriority(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


OPEN_ACTION_ITEM_STATUSES = (ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS)


class ActionItem(TimestampMixin, Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    #: Set when this action came out of a specific piece of advice, so the
    #: advice can later be judged by what its actions achieved.
    advice_id: Mapped[int | None] = mapped_column(
        ForeignKey("advice_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ActionItemStatus] = mapped_column(
        Enum(ActionItemStatus, name="action_item_status", native_enum=False, length=16),
        nullable=False,
        default=ActionItemStatus.OPEN,
    )
    priority: Mapped[ActionItemPriority] = mapped_column(
        Enum(ActionItemPriority, name="action_item_priority", native_enum=False, length=16),
        nullable=False,
        default=ActionItemPriority.MEDIUM,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")
    task = relationship("Task")
    issue = relationship("Issue")
    advice = relationship("AdviceRecord", back_populates="action_items")
    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by])
