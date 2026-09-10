"""Task dependency business logic.

Dependencies power the Gantt view. Links are constrained to a single project and
the graph is kept acyclic so downstream scheduling logic cannot loop forever.
"""

from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy.orm import Session

from app.models.task import TaskLink
from app.models.user import User
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.task_link import TaskLinkRepository
from app.schemas.task import TaskLinkCreate, TaskLinkUpdate
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    ProjectNotFoundError,
    TaskLinkNotFoundError,
    TaskNotFoundError,
)
from app.services.schedule_guard import ScheduleGuard


class TaskLinkService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TaskLinkRepository(db)
        self.tasks = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.audit = AuditService(db)

    def list_project_links(self, project_id: int) -> list[TaskLink]:
        if self.projects.get_by_id(project_id) is None:
            raise ProjectNotFoundError
        return self.repo.list_by_project(project_id)

    def get_link(self, link_id: int) -> TaskLink:
        link = self.repo.get_by_id(link_id)
        if link is None:
            raise TaskLinkNotFoundError
        return link

    def _guard(self, project_id: int, links: list[TaskLink], actor: User, action: str) -> None:
        """A dependency edit that forces other tasks to move needs a change proposal."""
        ScheduleGuard(self.db).check_links(project_id, links, actor, action=action)

    def _reassess(self, project_id: int) -> None:
        """The dependency graph changed, so the stored forecast no longer holds."""
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(project_id, with_forecast=True)

    def _would_create_cycle(self, project_id: int, source_id: int, target_id: int) -> bool:
        """True when target already reaches source, so the new edge closes a loop."""
        adjacency: dict[int, list[int]] = defaultdict(list)
        for link in self.repo.list_by_project(project_id):
            adjacency[link.source_id].append(link.target_id)

        queue = deque([target_id])
        seen = {target_id}
        while queue:
            current = queue.popleft()
            if current == source_id:
                return True
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return False

    def create_link(
        self,
        project_id: int,
        data: TaskLinkCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> TaskLink:
        if self.projects.get_by_id(project_id) is None:
            raise ProjectNotFoundError

        if data.source_id == data.target_id:
            msg = "A task cannot depend on itself"
            raise DomainValidationError(msg)

        source = self.tasks.get_by_id(data.source_id)
        target = self.tasks.get_by_id(data.target_id)
        if source is None or target is None:
            raise TaskNotFoundError
        if source.project_id != project_id or target.project_id != project_id:
            msg = "Both tasks must belong to the same project"
            raise DomainValidationError(msg)

        if self.repo.get_by_endpoints(data.source_id, data.target_id) is not None:
            msg = "This dependency already exists"
            raise DomainValidationError(msg)

        if self._would_create_cycle(project_id, data.source_id, data.target_id):
            msg = "This dependency would create a circular chain"
            raise DomainValidationError(msg)

        link = TaskLink(
            project_id=project_id,
            source_id=data.source_id,
            target_id=data.target_id,
            link_type=data.link_type,
            lag_days=data.lag_days,
        )
        self._guard(project_id, [*self.repo.list_by_project(project_id), link], actor, "新增依赖")
        self.repo.add(link)
        self._reassess(project_id)
        self.audit.record(
            action="task_link.create",
            resource_type="task_link",
            resource_id=str(link.id),
            user_id=actor.id,
            new_value=self.audit.task_link_to_dict(link),
            ip_address=ip_address,
        )
        return link

    def update_link(
        self,
        link_id: int,
        data: TaskLinkUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> TaskLink:
        link = self.get_link(link_id)
        old_snapshot = self.audit.task_link_to_dict(link)
        candidate = TaskLink(
            project_id=link.project_id,
            source_id=link.source_id,
            target_id=link.target_id,
            link_type=data.link_type,
            lag_days=link.lag_days if data.lag_days is None else data.lag_days,
        )
        self._guard(
            link.project_id,
            [
                candidate if row.id == link.id else row
                for row in self.repo.list_by_project(link.project_id)
            ],
            actor,
            "修改依赖",
        )
        link.link_type = data.link_type
        if data.lag_days is not None:
            link.lag_days = data.lag_days
        self.repo.save(link)
        self._reassess(link.project_id)
        self.audit.record(
            action="task_link.update",
            resource_type="task_link",
            resource_id=str(link.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value=self.audit.task_link_to_dict(link),
            ip_address=ip_address,
        )
        return link

    def delete_link(
        self,
        link_id: int,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> TaskLink:
        link = self.get_link(link_id)
        snapshot = self.audit.task_link_to_dict(link)
        self._guard(
            link.project_id,
            [row for row in self.repo.list_by_project(link.project_id) if row.id != link.id],
            actor,
            "删除依赖",
        )
        self.repo.delete(link)
        self._reassess(link.project_id)
        self.audit.record(
            action="task_link.delete",
            resource_type="task_link",
            resource_id=str(snapshot["id"]),
            user_id=actor.id,
            old_value=snapshot,
            ip_address=ip_address,
        )
        return link
