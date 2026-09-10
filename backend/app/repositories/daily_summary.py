"""DailyProjectSummary data access."""

from __future__ import annotations

from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.daily_project_summary import DailyProjectSummary


class DailySummaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, summary: DailyProjectSummary) -> DailyProjectSummary:
        self.db.add(summary)
        self.db.flush()
        return summary

    def get_by_project_and_date(
        self,
        project_id: int,
        summary_date: date,
    ) -> DailyProjectSummary | None:
        return self.db.scalar(
            select(DailyProjectSummary).where(
                DailyProjectSummary.project_id == project_id,
                DailyProjectSummary.summary_date == summary_date,
            )
        )

    def list_by_project(
        self,
        project_id: int,
        *,
        limit: int | None = None,
    ) -> list[DailyProjectSummary]:
        stmt = (
            select(DailyProjectSummary)
            .where(DailyProjectSummary.project_id == project_id)
            .order_by(desc(DailyProjectSummary.summary_date), desc(DailyProjectSummary.id))
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_latest(self, project_id: int) -> DailyProjectSummary | None:
        return self.db.scalar(
            select(DailyProjectSummary)
            .where(DailyProjectSummary.project_id == project_id)
            .order_by(desc(DailyProjectSummary.summary_date), desc(DailyProjectSummary.id))
            .limit(1)
        )
