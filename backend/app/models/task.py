"""Task ORM model."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SQLColumnExpression,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class TaskStatus(enum.StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskAiStatus(enum.StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    DELAYED = "DELAYED"


class TaskLinkType(enum.StrEnum):
    FINISH_TO_START = "FINISH_TO_START"
    START_TO_START = "START_TO_START"
    FINISH_TO_FINISH = "FINISH_TO_FINISH"
    START_TO_FINISH = "START_TO_FINISH"


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "planned_duration_days IS NULL OR planned_duration_days >= 1",
            name="ck_task_planned_duration",
        ),
        CheckConstraint(
            "remaining_duration_days IS NULL OR remaining_duration_days >= 0",
            name="ck_task_remaining_duration",
        ),
        CheckConstraint(
            "progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)",
            name="ck_tasks_progress_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    deliverable: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    planned_duration_days: Mapped[int | None] = mapped_column(Integer)
    remaining_duration_days: Mapped[int | None] = mapped_column(Integer)
    actual_start_date: Mapped[date | None] = mapped_column(Date)
    actual_finish_date: Mapped[date | None] = mapped_column(Date)
    earliest_start_date: Mapped[date | None] = mapped_column(Date)
    fixed_start_date: Mapped[date | None] = mapped_column(Date)
    fixed_due_date: Mapped[date | None] = mapped_column(Date)
    calendar_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_calendars.project_id", ondelete="RESTRICT")
    )
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="RESTRICT")
    )
    task_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_groups.id", ondelete="RESTRICT")
    )
    branch_suspended_status: Mapped[str | None] = mapped_column(String(16))
    branch_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("branch_options.id", ondelete="RESTRICT")
    )
    # Free-text work stream (e.g. "Medicinal Chemistry", "CRO"). The Gantt view groups
    # tasks by this value; unset tasks fall into a trailing "未分组" section.
    work_stream: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    # Optional: L3 execution tasks may be registered before dates are known.
    # Gantt falls back to a single-day / today placeholder when unset.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False, length=16),
        nullable=False,
        default=TaskStatus.TODO,
    )
    # Reserved for Phase 6+ AI analysis; never written by business rules in Phase 3.
    ai_status: Mapped[TaskAiStatus | None] = mapped_column(
        Enum(TaskAiStatus, name="task_ai_status", native_enum=False, length=16),
        nullable=True,
    )
    ai_risk_level: Mapped[TaskAiStatus | None] = mapped_column(
        Enum(TaskAiStatus, name="task_ai_risk_level", native_enum=False, length=16),
        nullable=True,
    )
    # Progress submitted before a plan/issue change is no longer current risk evidence.
    risk_context_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Alternative paths under one decision (e.g. compound A → switch to compound B).
    # All siblings share the same branch_root_id; exactly one should be active.
    branch_root_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    branch_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active_branch: Mapped[bool] = mapped_column(nullable=False, default=True)

    @hybrid_property
    def is_execution_active(self) -> bool:
        """Current unfinished work; inactive alternatives remain historical records."""
        return self.is_active_branch is not False and self.status in (
            TaskStatus.TODO,
            TaskStatus.IN_PROGRESS,
        )

    @is_execution_active.inplace.expression
    @classmethod
    def _is_execution_active_expression(cls) -> SQLColumnExpression[bool]:
        return and_(
            cls.is_active_branch.is_(True),
            cls.status.in_((TaskStatus.TODO, TaskStatus.IN_PROGRESS)),
        )

    project = relationship("Project", back_populates="tasks")
    owner = relationship("User", foreign_keys=[owner_id])
    branch_root = relationship("Task", remote_side="Task.id", foreign_keys=[branch_root_id])
    progress_updates = relationship(
        "ProgressUpdate",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    outgoing_links = relationship(
        "TaskLink",
        foreign_keys="TaskLink.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    incoming_links = relationship(
        "TaskLink",
        foreign_keys="TaskLink.target_id",
        back_populates="target",
        cascade="all, delete-orphan",
    )


class TaskLink(TimestampMixin, Base):
    """Dependency between two tasks of the same project, used by the Gantt view."""

    __tablename__ = "task_links"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", name="uq_task_links_source_target"),
        CheckConstraint("lag_days >= 0", name="ck_link_lag"),
        CheckConstraint("source_id <> target_id", name="ck_task_links_no_self_reference"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lag_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    link_type: Mapped[TaskLinkType] = mapped_column(
        Enum(TaskLinkType, name="task_link_type", native_enum=False, length=20),
        nullable=False,
        default=TaskLinkType.FINISH_TO_START,
    )

    project = relationship("Project")
    source = relationship("Task", foreign_keys=[source_id], back_populates="outgoing_links")
    target = relationship("Task", foreign_keys=[target_id], back_populates="incoming_links")
