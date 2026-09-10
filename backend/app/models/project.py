"""Project ORM model."""

from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Column, Date, Enum, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class ProjectStatus(enum.StrEnum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ProjectRiskLevel(enum.StrEnum):
    NORMAL = "NORMAL"
    AT_RISK = "AT_RISK"
    DELAYED = "DELAYED"


project_owners = Table(
    "project_owners",
    Base.metadata,
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("project_code", name="uq_projects_project_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_code: Mapped[str] = mapped_column(String(64), nullable=False)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Primary / lead owner — always also present in `owners`. Kept for
    # backward-compatible FK display and as the first entry when setting owners.
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", native_enum=False, length=16),
        nullable=False,
        default=ProjectStatus.ACTIVE,
    )
    risk_level: Mapped[ProjectRiskLevel] = mapped_column(
        Enum(ProjectRiskLevel, name="project_risk_level", native_enum=False, length=16),
        nullable=False,
        default=ProjectRiskLevel.NORMAL,
    )

    owner = relationship("User", foreign_keys=[owner_id])
    owners = relationship("User", secondary=project_owners, lazy="selectin")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
