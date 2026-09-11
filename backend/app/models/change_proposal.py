"""Reviewed plan changes.

The outbox rows they produce live in :mod:`app.models.notification`.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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


class ChangeProposal(TimestampMixin, Base):
    __tablename__ = "change_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    source: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    create_key: Mapped[str] = mapped_column(String(100))
    create_hash: Mapped[str] = mapped_column(String(64))
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    snapshot_token: Mapped[str | None] = mapped_column(String(64))
    digest: Mapped[str | None] = mapped_column(String(64))
    base_plan_version: Mapped[int | None] = mapped_column(Integer)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="RESTRICT")
    )
    apply_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("project_id", "created_by", "create_key", name="uq_proposal_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','VALIDATED','CONFIRMED','APPLIED','REJECTED','EXPIRED','FAILED')",
            name="ck_proposal_status",
        ),
        CheckConstraint("revision >= 1", name="ck_proposal_revision"),
    )
