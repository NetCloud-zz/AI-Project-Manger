"""Transactional notification intents, written inside the business transaction.

One row is one message to one person on one channel. The row is created by
whatever domain event justified it — an applied plan change, or a risk event
that just opened or escalated — and a separate worker is the only thing that
talks to the outside world.

``SENT`` only means the channel accepted the message. Whether a person read it
is unknown until they acknowledge it in this system.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

#: Applied change proposal. Payload carries the diff scoped to the recipient.
PLAN_CHANGE = "PLAN_CHANGE"
#: A deterministic risk detector fired, escalated, or stopped firing.
RISK_OPENED = "RISK_OPENED"
RISK_ESCALATED = "RISK_ESCALATED"
RISK_RESOLVED = "RISK_RESOLVED"

RISK_EVENT_TYPES = (RISK_OPENED, RISK_ESCALATED, RISK_RESOLVED)


class NotificationEvent(TimestampMixin, Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Set for PLAN_CHANGE. Exactly one source column is populated.
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("change_proposals.id", ondelete="CASCADE"), index=True
    )
    #: Set for the RISK_* types.
    risk_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_events.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), default=PLAN_CHANGE)
    #: Identifies the thing being announced, so the same news is never queued
    #: twice for the same person even if detection runs again.
    dedupe_key: Mapped[str] = mapped_column(String(160), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="console")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The channel returned no answer; the message may or may not have arrived.
    delivery_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("dedupe_key", "recipient_id", "channel", name="uq_notification_recipient"),
        CheckConstraint(
            "status IN ('QUEUED','SENT','FAILED','ACKNOWLEDGED')",
            name="ck_notification_status",
        ),
        CheckConstraint(
            "(proposal_id IS NULL) <> (risk_event_id IS NULL)",
            name="ck_notification_one_source",
        ),
    )


__all__ = [
    "PLAN_CHANGE",
    "RISK_ESCALATED",
    "RISK_EVENT_TYPES",
    "RISK_OPENED",
    "RISK_RESOLVED",
    "NotificationEvent",
]
