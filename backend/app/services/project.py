"""Project business logic."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.permissions import can_modify_project, can_modify_project_schedule
from app.models.project import Project
from app.models.user import User, UserRole, UserStatus
from app.repositories.project import ProjectRepository
from app.repositories.user import UserRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectDeleteRequest,
    ProjectOwnersUpdate,
    ProjectScheduleUpdate,
    ProjectUpdate,
)
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectCodeExistsError,
    ProjectNotFoundError,
)
from app.services.schedule_guard import ScheduleGuard


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProjectRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def _ensure_owner_exists(self, owner_id: int) -> User:
        owner = self.users.get_by_id(owner_id)
        if owner is None or owner.status != UserStatus.ACTIVE:
            raise OwnerNotFoundError
        return owner

    def _load_owners(self, owner_ids: list[int]) -> list[User]:
        loaded: list[User] = []
        for owner_id in owner_ids:
            loaded.append(self._ensure_owner_exists(owner_id))
        return loaded

    def _set_owners(
        self,
        project: Project,
        owner_ids: list[int],
        *,
        preferred_primary: int | None = None,
    ) -> None:
        """Replace the owner set. Every listed user is a full project owner.

        ``projects.owner_id`` remains a required FK for compatibility, but
        selection order must not promote anyone: keep the current primary when
        they remain in the set; otherwise use ``preferred_primary`` or the
        first remaining id.
        """
        if not owner_ids:
            raise DomainValidationError("At least one owner is required")
        owners = self._load_owners(list(dict.fromkeys(owner_ids)))
        owner_id_set = {owner.id for owner in owners}
        if preferred_primary is not None and preferred_primary in owner_id_set:
            project.owner_id = preferred_primary
        elif project.owner_id not in owner_id_set:
            project.owner_id = owners[0].id
        project.owners = owners

    def _validate_create(self, data: ProjectCreate, actor: User) -> None:
        if actor.role == UserRole.PROJECT_OWNER and data.owner_id != actor.id:
            msg = "Project owners may only create projects assigned to themselves"
            raise DomainValidationError(msg)

    def _validate_date_range(self, start: date | None, target: date | None) -> None:
        if start and target and start > target:
            msg = "Project start date cannot be later than the target date"
            raise DomainValidationError(msg)

    def create_project(
        self,
        data: ProjectCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Project:
        self._validate_create(data, actor)
        if self.repo.get_by_code(data.project_code):
            raise ProjectCodeExistsError
        self._validate_date_range(data.start_date, data.target_date)

        owner_ids = list(data.owner_ids or [])
        if data.owner_id not in owner_ids:
            owner_ids.append(data.owner_id)

        project = Project(
            project_code=data.project_code,
            project_name=data.project_name,
            goal=data.goal,
            owner_id=data.owner_id,
            start_date=data.start_date,
            target_date=data.target_date,
            status=data.status,
            risk_level=data.risk_level,
        )
        self.repo.add(project)
        self._set_owners(project, owner_ids, preferred_primary=data.owner_id)
        self.audit.record(
            action="project.create",
            resource_type="project",
            resource_id=str(project.id),
            user_id=actor.id,
            new_value=self.audit.project_to_dict(project),
            ip_address=ip_address,
        )
        return self.repo.get_by_id(project.id) or project

    def list_projects(self, actor: User) -> list[Project]:
        return self.repo.list_for_user(actor)

    def get_project(self, project_id: int) -> Project:
        project = self.repo.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError
        return project

    def get_project_by_code(self, project_code: str) -> Project:
        project = self.repo.get_by_code(project_code)
        if project is None:
            raise ProjectNotFoundError
        return project

    def update_project(
        self,
        project_id: int,
        data: ProjectUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Project:
        project = self.get_project(project_id)
        old_snapshot = self.audit.project_to_dict(project)
        updates = data.model_dump(exclude_unset=True)
        owner_ids = updates.pop("owner_ids", None)
        preferred_primary: int | None = None

        if "owner_id" in updates and owner_ids is None:
            # Explicit owner_id change: ensure they are in the owner set.
            new_primary = updates["owner_id"]
            self._ensure_owner_exists(new_primary)
            current_ids = [o.id for o in project.owners] or [project.owner_id]
            if new_primary not in current_ids:
                current_ids.append(new_primary)
            owner_ids = current_ids
            preferred_primary = new_primary
            updates.pop("owner_id", None)
        elif "owner_id" in updates:
            preferred_primary = updates.pop("owner_id")

        for field, value in updates.items():
            setattr(project, field, value)

        if owner_ids is not None:
            self._set_owners(project, owner_ids, preferred_primary=preferred_primary)

        self.repo.save(project)
        new_snapshot = self.audit.project_to_dict(project)

        self.audit.record(
            action="project.update",
            resource_type="project",
            resource_id=str(project.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value=new_snapshot,
            ip_address=ip_address,
        )
        if "status" in updates and updates["status"] != old_snapshot["status"]:
            self.audit.record(
                action="project.status_change",
                resource_type="project",
                resource_id=str(project.id),
                user_id=actor.id,
                old_value={"status": old_snapshot["status"]},
                new_value={"status": project.status.value},
                ip_address=ip_address,
            )
        if new_snapshot.get("owner_ids") != old_snapshot.get("owner_ids") or (
            new_snapshot.get("owner_id") != old_snapshot.get("owner_id")
        ):
            self.audit.record(
                action="project.owner_change",
                resource_type="project",
                resource_id=str(project.id),
                user_id=actor.id,
                old_value={
                    "owner_id": old_snapshot["owner_id"],
                    "owner_ids": old_snapshot.get("owner_ids"),
                },
                new_value={
                    "owner_id": project.owner_id,
                    "owner_ids": new_snapshot.get("owner_ids"),
                },
                ip_address=ip_address,
            )
        return self.repo.get_by_id(project.id) or project

    def update_owners(
        self,
        project_id: int,
        data: ProjectOwnersUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Project:
        return self.update_project(
            project_id,
            ProjectUpdate(owner_ids=data.owner_ids),
            actor=actor,
            ip_address=ip_address,
        )

    def update_schedule(
        self,
        project_id: int,
        data: ProjectScheduleUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Project:
        project = self.get_project(project_id)
        old_snapshot = self.audit.project_to_dict(project)

        if not can_modify_project_schedule(actor, project, self.db):
            raise PermissionDeniedError("You cannot modify this project schedule")
        payload = data.model_dump(exclude_unset=True)
        new_start = payload.get("start_date", project.start_date)
        new_target = payload.get("target_date", project.target_date)
        self._validate_date_range(new_start, new_target)
        # Moving the project start acts as a floor for every unstarted task, so
        # it can silently reschedule work. Moving the target only changes the
        # commitment we compare against, which is this endpoint's whole point.
        if "start_date" in payload:
            ScheduleGuard(self.db).check_project_start(project, data.start_date, actor)

        # Use explicit None-vs-unset: fields present in the payload overwrite.
        payload = data.model_dump(exclude_unset=True)
        if "start_date" in payload:
            project.start_date = data.start_date
        if "target_date" in payload:
            project.target_date = data.target_date

        self.repo.save(project)
        new_snapshot = self.audit.project_to_dict(project)
        self.audit.record(
            action="project.schedule_change",
            resource_type="project",
            resource_id=str(project.id),
            user_id=actor.id,
            old_value={
                "start_date": old_snapshot.get("start_date"),
                "target_date": old_snapshot.get("target_date"),
            },
            new_value={
                "start_date": new_snapshot.get("start_date"),
                "target_date": new_snapshot.get("target_date"),
                "change_reason": data.change_reason,
            },
            ip_address=ip_address,
        )
        from app.services.risk_engine import RiskEngine

        # The target date is what the forecast is judged against, so a change
        # here can open or close a delay risk immediately.
        RiskEngine(self.db).refresh_project(project.id, with_forecast=True)
        return self.repo.get_by_id(project.id) or project

    def _clear_project_restrict_refs(self, project_id: int) -> None:
        """Null RESTRICT FKs so a hard delete of the project can cascade cleanly."""
        from sqlalchemy import update

        from app.models.change_proposal import ChangeProposal
        from app.models.planning import BranchGroup, TaskGroup
        from app.models.task import Task

        self.db.execute(
            update(ChangeProposal)
            .where(ChangeProposal.project_id == project_id)
            .values(applied_version_id=None)
        )
        self.db.execute(
            update(BranchGroup)
            .where(BranchGroup.project_id == project_id)
            .values(entry_task_id=None, exit_task_id=None)
        )
        self.db.execute(
            update(Task)
            .where(Task.project_id == project_id)
            .values(
                calendar_id=None,
                milestone_id=None,
                task_group_id=None,
                branch_option_id=None,
            )
        )
        self.db.execute(
            update(TaskGroup).where(TaskGroup.project_id == project_id).values(parent_id=None)
        )
        self.db.flush()

    def delete_project(
        self,
        project_id: int,
        data: ProjectDeleteRequest,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        project = self.get_project(project_id)
        if not can_modify_project(actor, project, self.db):
            raise PermissionDeniedError("只有项目负责人或管理员可以删除项目")

        from app.models.task import Task
        from sqlalchemy import func, select

        task_count = int(
            self.db.scalar(
                select(func.count()).select_from(Task).where(Task.project_id == project.id)
            )
            or 0
        )
        old_snapshot = self.audit.project_to_dict(project)
        old_snapshot["task_count"] = task_count

        self.audit.record(
            action="project.delete",
            resource_type="project",
            resource_id=str(project.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value={"deleted": True, "reason": data.reason},
            ip_address=ip_address,
        )
        self._clear_project_restrict_refs(project.id)
        self.repo.delete(project)
