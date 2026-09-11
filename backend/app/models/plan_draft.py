"""Conversational project plan drafts.

A draft is a staging area, not a plan. Nothing in it affects tracking, risk or
notifications until it is published, and publishing writes the whole project in
one transaction.
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


class PlanDraft(TimestampMixin, Base):
    __tablename__ = "plan_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    digest: Mapped[str | None] = mapped_column(String(64))
    create_key: Mapped[str] = mapped_column(String(100))
    publish_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("created_by", "create_key", name="uq_plan_draft_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','REVIEWED','PUBLISHED','DISCARDED','FAILED')",
            name="ck_plan_draft_status",
        ),
        CheckConstraint("revision >= 1", name="ck_plan_draft_revision"),
    )
