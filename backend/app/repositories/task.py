"""Task data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.task import Task


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, task_id: int) -> Task | None:
        return self.db.scalar(
            select(Task)
            .options(joinedload(Task.owner), joinedload(Task.project))
            .where(Task.id == task_id)
        )

    def list_by_project(self, project_id: int) -> list[Task]:
        stmt = (
            select(Task)
            .options(joinedload(Task.owner))
            .where(Task.project_id == project_id)
            .order_by(Task.due_date, Task.id)
        )
        return list(self.db.scalars(stmt).unique().all())

    def list_by_owner(self, owner_id: int) -> list[Task]:
        stmt = (
            select(Task)
            .options(joinedload(Task.owner), joinedload(Task.project))
            .where(Task.owner_id == owner_id)
            .order_by(Task.due_date, Task.id)
        )
        return list(self.db.scalars(stmt).unique().all())

    def add(self, task: Task) -> Task:
        self.db.add(task)
        self.db.flush()
        return task

    def save(self, task: Task) -> Task:
        self.db.add(task)
        self.db.flush()
        return task

    def delete(self, task: Task) -> None:
        self.db.delete(task)
        self.db.flush()

    def list_active_tasks(self) -> list[Task]:
        stmt = (
            select(Task)
            .options(joinedload(Task.owner), joinedload(Task.project))
            .where(Task.is_execution_active)
            .order_by(Task.due_date, Task.id)
        )
        return list(self.db.scalars(stmt).unique().all())

    def list_active_by_project_ids(self, project_ids: list[int]) -> dict[int, list[Task]]:
        if not project_ids:
            return {}
        stmt = (
            select(Task)
            .where(
                Task.project_id.in_(project_ids),
                Task.is_execution_active,
            )
            .order_by(Task.due_date, Task.id)
        )
        tasks = list(self.db.scalars(stmt).all())
        grouped: dict[int, list[Task]] = {project_id: [] for project_id in project_ids}
        for task in tasks:
            grouped[task.project_id].append(task)
        return grouped
