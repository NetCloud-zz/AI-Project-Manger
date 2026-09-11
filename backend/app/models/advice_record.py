"""Versioned advice on an issue, with what it was based on and what came of it.

``Issue.suggested_solution`` holds only the latest text. A record keeps every
version, the evidence each version was built from, whether a person adopted it,
and whether adopting it actually helped — so advice can be evaluated instead of
just admired.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class AdviceStatus(enum.StrEnum):
    #: Produced, nobody has decided anything yet.
    PROPOSED = "PROPOSED"
    #: A person accepted it; follow-up work is linked to this record.
    ADOPTED = "ADOPTED"
    #: A person rejected it, with a reason.
    REJECTED = "REJECTED"
    #: A newer version replaced it before anyone acted.
    SUPERSEDED = "SUPERSEDED"


class AdviceOutcome(enum.StrEnum):
    EFFECTIVE = "EFFECTIVE"
    PARTIAL = "PARTIAL"
    INEFFECTIVE = "INEFFECTIVE"


class AdviceRecord(TimestampMixin, Base):
    __tablename__ = "advice_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    #: 1-based, per issue. A new generation never overwrites an older version.
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[AdviceStatus] = mapped_column(
        Enum(AdviceStatus, name="advice_status", native_enum=False, length=16),
        default=AdviceStatus.PROPOSED,
        index=True,
    )
    #: Structured advice: summary, causes, checks, options, impact, gaps.
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    #: [{source_type, source_id, updated_at, detail}] — what the advice read.
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    #: Which parts of the project the evidence covered, and what was missing.
    coverage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    #: Fingerprint of the evidence set, so a stale adoption can be spotted.
    context_digest: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(120))
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    #: Change proposal created because of this advice, if the plan had to move.
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("change_proposals.id", ondelete="SET NULL")
    )

    outcome: Mapped[AdviceOutcome | None] = mapped_column(
        Enum(AdviceOutcome, name="advice_outcome", native_enum=False, length=16)
    )
    #: Whether the underlying issue was actually resolved, recorded separately
    #: from whether the advice was any good.
    issue_resolved: Mapped[bool | None] = mapped_column()
    outcome_note: Mapped[str | None] = mapped_column(Text)
    evaluated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issue = relationship("Issue")
    action_items = relationship(
        "ActionItem", back_populates="advice", order_by="ActionItem.id", viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("issue_id", "version", name="uq_advice_version"),
        CheckConstraint("version >= 1", name="ck_advice_version"),
        Index("ix_advice_records_issue_status", "issue_id", "status"),
    )
