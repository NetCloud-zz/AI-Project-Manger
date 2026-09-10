"""S1 planning records. Task dates remain the current plan; snapshots are immutable."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="CONTRIBUTOR")
    receive_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("role IN ('CONTRIBUTOR', 'OBSERVER')", name="ck_member_role"),
    )


class TaskParticipant(TimestampMixin, Base):
    __tablename__ = "task_participants"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="COLLABORATOR")
    __table_args__ = (
        CheckConstraint("role IN ('COLLABORATOR', 'WATCHER')", name="ck_participant_role"),
    )


class WorkCalendar(TimestampMixin, Base):
    __tablename__ = "work_calendars"
    # One versioned calendar per project; task calendar_id refers to this project key.
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(120), default="项目工作日历")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])
    exceptions: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint("version >= 1", name="ck_calendar_version"),)


class Milestone(TimestampMixin, Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    deliverable: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    achieved_date: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED', 'ACHIEVED', 'CANCELLED')", name="ck_milestone_status"
        ),
    )


class TaskGroup(TimestampMixin, Base):
    __tablename__ = "task_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("task_groups.id", ondelete="RESTRICT"))


class BranchGroup(TimestampMixin, Base):
    __tablename__ = "branch_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    entry_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", use_alter=True, name="fk_branch_entry", ondelete="RESTRICT")
    )
    exit_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", use_alter=True, name="fk_branch_exit", ondelete="RESTRICT")
    )
    legacy_root_id: Mapped[int | None] = mapped_column(Integer, unique=True)


class BranchOption(TimestampMixin, Base):
    __tablename__ = "branch_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("branch_groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("group_id", "name", name="uq_branch_option_name"),)


class PlanVersion(TimestampMixin, Base):
    __tablename__ = "plan_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24), default="SNAPSHOT")
    reason: Mapped[str] = mapped_column(String(2000))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_plan_version"),)
