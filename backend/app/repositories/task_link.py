"""Task dependency data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.task import TaskLink


class TaskLinkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, link_id: int) -> TaskLink | None:
        return self.db.scalar(select(TaskLink).where(TaskLink.id == link_id))

    def list_by_project(self, project_id: int) -> list[TaskLink]:
        stmt = select(TaskLink).where(TaskLink.project_id == project_id).order_by(TaskLink.id)
        return list(self.db.scalars(stmt).all())

    def get_by_endpoints(self, source_id: int, target_id: int) -> TaskLink | None:
        return self.db.scalar(
            select(TaskLink).where(
                TaskLink.source_id == source_id,
                TaskLink.target_id == target_id,
            )
        )

    def add(self, link: TaskLink) -> TaskLink:
        self.db.add(link)
        self.db.flush()
        return link

    def save(self, link: TaskLink) -> TaskLink:
        self.db.add(link)
        self.db.flush()
        return link

    def delete(self, link: TaskLink) -> None:
        self.db.delete(link)
        self.db.flush()
