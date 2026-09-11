"""Tracked risk records.

``Task.ai_status`` and ``Project.risk_level`` only say what the risk is *now*.
A risk event says why, on what evidence, since when, and how it was closed —
which is what a person needs in order to argue with it.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class RiskEventType(enum.StrEnum):
    #: The due date has already passed. A fact, not a prediction.
    OVERDUE = "OVERDUE"
    #: The schedule engine predicts the project finishes after its target date.
    FORECAST_DELAY = "FORECAST_DELAY"
    #: An open HIGH/CRITICAL problem in R&D execution.
    ISSUE = "ISSUE"
    #: The plan cannot be judged because required facts are missing.
    MISSING_DATA = "MISSING_DATA"


class RiskEventLevel(enum.StrEnum):
    AT_RISK = "AT_RISK"
    DELAYED = "DELAYED"


class RiskEventStatus(enum.StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


#: Deterministic detectors reopen the same event instead of creating a new one.
RISK_EVENT_TYPES = tuple(item.value for item in RiskEventType)


class RiskEvent(TimestampMixin, Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    #: Null for project-level risks such as a forecast overrun.
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"))
    event_type: Mapped[RiskEventType] = mapped_column(
        Enum(RiskEventType, name="risk_event_type", native_enum=False, length=24)
    )
    #: Stable identity of one concrete risk, e.g. "OVERDUE:task:12".
    dedupe_key: Mapped[str] = mapped_column(String(120))
    level: Mapped[RiskEventLevel] = mapped_column(
        Enum(RiskEventLevel, name="risk_event_level", native_enum=False, length=16)
    )
    status: Mapped[RiskEventStatus] = mapped_column(
        Enum(RiskEventStatus, name="risk_event_status", native_enum=False, length=16),
        default=RiskEventStatus.OPEN,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300))
    #: Why the detector fired, in the words a reviewer would use.
    cause: Mapped[str] = mapped_column(Text)
    #: [{source_type, source_id, updated_at, detail}] — every claim points at a record.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    #: The date the risk bites: a due date, or a predicted finish date.
    impact_date: Mapped[date | None] = mapped_column(Date)
    #: How much later than committed, in days. Null when it cannot be quantified.
    impact_days: Mapped[int | None] = mapped_column()
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Why it was closed. Auto-closed events say which detector stopped firing.
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    project = relationship("Project")
    task = relationship("Task")
    owner = relationship("User", foreign_keys=[owner_id])

    __table_args__ = (
        # One open row per concrete risk; a resolved one may be superseded later.
        UniqueConstraint("project_id", "dedupe_key", name="uq_risk_event_key"),
        CheckConstraint("impact_days IS NULL OR impact_days >= 0", name="ck_risk_event_impact"),
        Index("ix_risk_events_project_status", "project_id", "status"),
    )
