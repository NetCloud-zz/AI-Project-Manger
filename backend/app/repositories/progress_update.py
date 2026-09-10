"""ProgressUpdate data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.models.progress_update import ProgressUpdate
from app.models.task import Task


class ProgressUpdateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, progress: ProgressUpdate) -> ProgressUpdate:
        self.db.add(progress)
        self.db.flush()
        return progress

    def get_by_id(self, progress_id: int) -> ProgressUpdate | None:
        return self.db.get(ProgressUpdate, progress_id)

    def list_by_task(self, task_id: int, *, limit: int | None = None) -> list[ProgressUpdate]:
        stmt = (
            select(ProgressUpdate)
            .where(ProgressUpdate.task_id == task_id)
            .order_by(desc(ProgressUpdate.created_at), desc(ProgressUpdate.id))
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_recent_by_project(self, project_id: int, *, limit: int = 20) -> list[ProgressUpdate]:
        stmt = (
            select(ProgressUpdate)
            .join(Task, ProgressUpdate.task_id == Task.id)
            .where(Task.project_id == project_id)
            .options(joinedload(ProgressUpdate.task), joinedload(ProgressUpdate.user))
            .order_by(desc(ProgressUpdate.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def latest_created_at_by_task_ids(self, task_ids: list[int]) -> dict[int, datetime]:
        if not task_ids:
            return {}
        stmt = (
            select(
                ProgressUpdate.task_id,
                ProgressUpdate.created_at,
            )
            .where(ProgressUpdate.task_id.in_(task_ids))
            .order_by(ProgressUpdate.task_id, desc(ProgressUpdate.created_at))
        )
        latest: dict[int, datetime] = {}
        for task_id, created_at in self.db.execute(stmt):
            if task_id not in latest:
                latest[task_id] = created_at
        return latest

    def list_task_ids_with_owner_progress_between(
        self,
        task_ids: list[int],
        *,
        owner_id: int,
        start: datetime,
        end: datetime,
    ) -> set[int]:
        if not task_ids:
            return set()
        stmt = (
            select(ProgressUpdate.task_id)
            .where(
                ProgressUpdate.task_id.in_(task_ids),
                ProgressUpdate.user_id == owner_id,
                ProgressUpdate.created_at >= start,
                ProgressUpdate.created_at < end,
            )
            .distinct()
        )
        return set(self.db.scalars(stmt).all())
