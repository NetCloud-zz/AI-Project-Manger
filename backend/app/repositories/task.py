"""Task data access."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.project import Project
from app.models.task import Task, TaskStatus


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, task_id: int) -> Task | None:
        return self.db.scalar(
            select(Task)
            .options(joinedload(Task.owner), joinedload(Task.project))
            .where(Task.id == task_id)
        )

    def get_by_id_for_update(self, task_id: int) -> Task | None:
        """Lock the task row for the rest of the transaction (delete/progress races)."""
        task = self.db.scalar(select(Task).where(Task.id == task_id).with_for_update())
        if task is None:
            return None
        # Ensure relationships used by callers are available after the lock.
        _ = task.owner
        _ = task.project
        return task

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

    def list_by_owner_paged(
        self,
        owner_id: int,
        *,
        status: TaskStatus | None = None,
        q: str | None = None,
        sort: str = "due",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Task], int]:
        """Server-side filter/sort/page for /tasks/my."""
        filters = [Task.owner_id == owner_id]
        if status is not None:
            filters.append(Task.status == status)
        keyword = (q or "").strip()
        needs_project = bool(keyword) or sort == "project"
        if keyword:
            like = f"%{keyword}%"
            filters.append(
                or_(
                    Task.task_name.ilike(like),
                    Project.project_code.ilike(like),
                    Project.project_name.ilike(like),
                )
            )

        count_stmt = select(func.count(Task.id)).where(*filters)
        if needs_project:
            count_stmt = count_stmt.join(Project, Project.id == Task.project_id)
        total = int(self.db.scalar(count_stmt) or 0)

        order = {
            "name": (Task.task_name.asc(), Task.id.asc()),
            "project": (Project.project_code.asc(), Task.id.asc()),
            "due": (Task.due_date.asc().nulls_last(), Task.id.asc()),
        }.get(sort, (Task.due_date.asc().nulls_last(), Task.id.asc()))

        stmt = select(Task).options(joinedload(Task.owner), joinedload(Task.project))
        if needs_project or sort == "project":
            stmt = stmt.join(Project, Project.id == Task.project_id)
        stmt = stmt.where(*filters).order_by(*order).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).unique().all()), total

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
