"""Daily project summary ORM model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin


class DailyProjectSummary(TimestampMixin, Base):
    __tablename__ = "daily_project_summaries"
    __table_args__ = (
        UniqueConstraint("project_id", "summary_date", name="uq_daily_summary_project_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_summary: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    management_attention: Mapped[str] = mapped_column(Text, nullable=False)

    project = relationship("Project")
