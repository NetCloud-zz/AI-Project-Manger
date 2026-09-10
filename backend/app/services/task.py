"""Task business logic."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.permissions import can_modify_task_core
from app.models.task import Task, TaskStatus
from app.models.user import User, UserStatus
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.schemas.task import (
    TaskBranchActivate,
    TaskBranchCreate,
    TaskCreate,
    TaskDeleteRequest,
    TaskPlanningFields,
    TaskUpdate,
)
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.schedule_guard import ScheduleGuard


def _normalize_work_stream(value: str | None) -> str | None:
    """Collapse blank input to NULL so grouping never shows an empty section."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def _ensure_owner_exists(self, owner_id: int) -> None:
        owner = self.users.get_by_id(owner_id)
        if owner is None or owner.status != UserStatus.ACTIVE:
            raise OwnerNotFoundError

    def _validate_due_date(self, due_date: date | None, project_target: date | None) -> None:
        if due_date is None:
            return
        if project_target and due_date > project_target:
            msg = "Task due date cannot be later than the project target date"
            raise DomainValidationError(msg)

    def _validate_date_range(self, start_date: date | None, due_date: date | None) -> None:
        if start_date and due_date and start_date > due_date:
            msg = "Task start date cannot be later than the due date"
            raise DomainValidationError(msg)

    def _validate_planning(self, project_id: int, values: dict) -> None:
        from app.models.planning import Milestone, TaskGroup, WorkCalendar

        for key, model in (
            ("calendar_id", WorkCalendar),
            ("milestone_id", Milestone),
            ("task_group_id", TaskGroup),
        ):
            value = values.get(key)
            if value is not None:
                row: Any = self.db.get(model, value)
                if row is None or row.project_id != project_id:
                    raise DomainValidationError(f"{key} must belong to this project")
        start, due = values.get("start_date"), values.get("due_date")
        earliest, fixed_start, fixed_due = (
            values.get(key) for key in ("earliest_start_date", "fixed_start_date", "fixed_due_date")
        )
        if earliest and (
            (start is not None and start < earliest) or (due is not None and due < earliest)
        ):
            raise DomainValidationError("Current dates precede earliest_start_date")
        if fixed_start is not None and start != fixed_start:
            raise DomainValidationError("start_date must equal fixed_start_date")
        if fixed_due is not None and due != fixed_due:
            raise DomainValidationError("due_date must equal fixed_due_date")
        actual_start, actual_finish = (
            values.get("actual_start_date"),
            values.get("actual_finish_date"),
        )
        if actual_finish and (not actual_start or actual_finish < actual_start):
            raise DomainValidationError("Actual finish requires an earlier or equal actual start")
        if actual_finish and values.get("status") != TaskStatus.COMPLETED:
            raise DomainValidationError("Actual finish is only valid for a completed task")
        planned, remaining = (
            values.get("planned_duration_days"),
            values.get("remaining_duration_days"),
        )
        if planned is not None and planned < 1 or remaining is not None and remaining < 0:
            raise DomainValidationError("Invalid workday duration")

    def create_task(
        self,
        project_id: int,
        data: TaskCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Task:
        project = self.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError
        self._ensure_owner_exists(data.owner_id)
        self._validate_due_date(data.due_date, project.target_date)
        self._validate_date_range(data.start_date, data.due_date)

        self._validate_planning(project_id, data.model_dump())
        task = Task(
            **data.model_dump(include=set(TaskPlanningFields.model_fields)),
            project_id=project_id,
            task_name=data.task_name,
            work_stream=_normalize_work_stream(data.work_stream),
            owner_id=data.owner_id,
            start_date=data.start_date,
            due_date=data.due_date,
            progress_percent=data.progress_percent,
            status=data.status,
        )
        if task.status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now(UTC)

        self.repo.add(task)
        self.audit.record(
            action="task.create",
            resource_type="task",
            resource_id=str(task.id),
            user_id=actor.id,
            new_value=self.audit.task_to_dict(task),
            ip_address=ip_address,
        )
        return self.repo.get_by_id(task.id) or task

    def list_project_tasks(self, project_id: int) -> list[Task]:
        if self.projects.get_by_id(project_id) is None:
            raise ProjectNotFoundError
        return self.repo.list_by_project(project_id)

    def list_my_tasks(self, user: User) -> list[Task]:
        return self.repo.list_by_owner(user.id)

    def get_task(self, task_id: int) -> Task:
        task = self.repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        return task

    def update_task(
        self,
        task_id: int,
        data: TaskUpdate,
        *,
        actor: User,
        allow_core_fields: bool,
        ip_address: str | None = None,
        expected_version: int | None = None,
    ) -> Task:
        task = self.get_task(task_id)
        project = task.project
        if project is None:
            raise ProjectNotFoundError

        if expected_version is not None and int(getattr(task, "version", 1) or 1) != int(
            expected_version
        ):
            from app.services.exceptions import VersionConflictError

            raise VersionConflictError(
                "VERSION_CONFLICT",
                current={
                    "id": task.id,
                    "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                    "progress_percent": task.progress_percent,
                    "version": int(getattr(task, "version", 1) or 1),
                },
            )

        old_snapshot = self.audit.task_to_dict(task)
        old_status = task.status
        updates = data.model_dump(exclude_unset=True)

        core_fields = {"task_name", "work_stream", "owner_id", "start_date", "due_date"} | set(
            TaskPlanningFields.model_fields
        )
        requested_core = core_fields.intersection(updates)
        if requested_core and not allow_core_fields:
            msg = f"You cannot modify task fields: {', '.join(sorted(requested_core))}"
            raise DomainValidationError(msg)

        self._validate_planning(
            project.id,
            {
                **{key: getattr(task, key) for key in TaskPlanningFields.model_fields},
                "start_date": task.start_date,
                "due_date": task.due_date,
                "status": task.status,
                **updates,
            },
        )
        if "work_stream" in updates:
            updates["work_stream"] = _normalize_work_stream(updates["work_stream"])
        if "owner_id" in updates:
            self._ensure_owner_exists(updates["owner_id"])
        if "due_date" in updates:
            self._validate_due_date(updates["due_date"], project.target_date)
        if "start_date" in updates or "due_date" in updates:
            self._validate_date_range(
                updates.get("start_date", task.start_date),
                updates.get("due_date", task.due_date),
            )
        # A plan edit that ripples into other tasks belongs in a change proposal;
        # recording a fact never does. See services/schedule_guard.py.
        ScheduleGuard(self.db).check_task_edit(task, updates, actor, action="这次改期")

        if "status" in updates:
            # An explicit status edit supersedes a previous route-switch cancellation.
            task.branch_suspended_status = None
            new_status = updates["status"]
            if new_status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now(UTC)
            elif old_status == TaskStatus.COMPLETED and new_status != TaskStatus.COMPLETED:
                task.completed_at = None

        for field, value in updates.items():
            setattr(task, field, value)

        task.version = int(getattr(task, "version", 1) or 1) + 1
        self.repo.save(task)
        new_snapshot = self.audit.task_to_dict(task)

        self.audit.record(
            action="task.update",
            resource_type="task",
            resource_id=str(task.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value=new_snapshot,
            ip_address=ip_address,
        )
        if "status" in updates and updates["status"] != old_snapshot["status"]:
            self.audit.record(
                action="task.status_change",
                resource_type="task",
                resource_id=str(task.id),
                user_id=actor.id,
                old_value={"status": old_snapshot["status"]},
                new_value={"status": task.status.value},
                ip_address=ip_address,
            )
        if "owner_id" in updates and updates["owner_id"] != old_snapshot["owner_id"]:
            self.audit.record(
                action="task.owner_change",
                resource_type="task",
                resource_id=str(task.id),
                user_id=actor.id,
                old_value={"owner_id": old_snapshot["owner_id"]},
                new_value={"owner_id": task.owner_id},
                ip_address=ip_address,
            )
        if "due_date" in updates and updates["due_date"] != old_snapshot["due_date"]:
            self.audit.record(
                action="task.due_date_change",
                resource_type="task",
                resource_id=str(task.id),
                user_id=actor.id,
                old_value={"due_date": old_snapshot["due_date"]},
                new_value={"due_date": task.due_date.isoformat() if task.due_date else None},
                ip_address=ip_address,
            )
        if "start_date" in updates and new_snapshot["start_date"] != old_snapshot["start_date"]:
            self.audit.record(
                action="task.start_date_change",
                resource_type="task",
                resource_id=str(task.id),
                user_id=actor.id,
                old_value={"start_date": old_snapshot["start_date"]},
                new_value={"start_date": new_snapshot["start_date"]},
                ip_address=ip_address,
            )
        relevant = {
            "due_date",
            "start_date",
            "task_name",
            "work_stream",
            "owner_id",
            "status",
        } | set(TaskPlanningFields.model_fields)
        if any(old_snapshot.get(key) != new_snapshot.get(key) for key in relevant):
            from app.services.risk_engine import RiskEngine

            # Anything that moves the schedule invalidates the stored forecast,
            # so recompute it here instead of leaving a stale verdict until the
            # next daily scan.
            RiskEngine(self.db).refresh_project(
                task.project_id,
                invalidate_task_ids={task.id},
                with_forecast=ScheduleGuard.touches_schedule(old_snapshot, new_snapshot),
            )
        return self.repo.get_by_id(task.id) or task

    def list_branch_siblings(self, task_id: int) -> list[Task]:
        task = self.get_task(task_id)
        root_id = task.branch_root_id or task.id
        return [
            item
            for item in self.repo.list_by_project(task.project_id)
            if (item.branch_root_id or item.id) == root_id
        ]

    def create_branch(
        self,
        source_task_id: int,
        data: TaskBranchCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Task:
        source = self.get_task(source_task_id)
        if source.branch_option_id is not None:
            raise DomainValidationError("Use the branch-group editor for grouped tasks")
        project = source.project
        if project is None:
            raise ProjectNotFoundError

        owner_id = data.owner_id or source.owner_id
        self._ensure_owner_exists(owner_id)
        due_date = data.due_date or source.due_date
        start_date = data.start_date if data.start_date is not None else source.start_date
        self._validate_due_date(due_date, project.target_date)
        self._validate_date_range(start_date, due_date)

        root_id = source.branch_root_id or source.id
        if source.branch_root_id is None:
            source.branch_root_id = source.id
            source.branch_label = source.branch_label or "主线"
            source.is_active_branch = True
            self.repo.save(source)

        branch = Task(
            project_id=source.project_id,
            task_name=data.task_name,
            work_stream=_normalize_work_stream(data.work_stream) or source.work_stream,
            owner_id=owner_id,
            start_date=start_date,
            due_date=due_date,
            progress_percent=0,
            status=TaskStatus.TODO,
            branch_root_id=root_id,
            branch_label=data.branch_label.strip(),
            is_active_branch=False,
        )
        self.repo.add(branch)

        self.audit.record(
            action="task.branch_create",
            resource_type="task",
            resource_id=str(branch.id),
            user_id=actor.id,
            old_value={"from_task_id": source.id},
            new_value={
                **self.audit.task_to_dict(branch),
                "reason": data.reason.strip(),
            },
            ip_address=ip_address,
        )

        if data.activate:
            return self.activate_branch(
                branch.id,
                TaskBranchActivate(reason=data.reason),
                actor=actor,
                ip_address=ip_address,
            )
        return self.repo.get_by_id(branch.id) or branch

    def activate_branch(
        self,
        task_id: int,
        data: TaskBranchActivate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Task:
        task = self.get_task(task_id)
        if task.branch_option_id is not None:
            raise DomainValidationError("Use the branch-group selection endpoint for grouped tasks")
        root_id = task.branch_root_id or task.id
        siblings = [
            item
            for item in self.repo.list_by_project(task.project_id)
            if (item.branch_root_id or item.id) == root_id
        ]
        if not siblings:
            siblings = [task]

        previously_active = [item for item in siblings if item.is_active_branch]
        for sibling in siblings:
            sibling.is_active_branch = sibling.id == task.id
            if sibling.id != task.id and sibling.status not in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                sibling.status = TaskStatus.CANCELLED
            self.repo.save(sibling)

        task.is_active_branch = True
        if task.status == TaskStatus.CANCELLED:
            task.status = TaskStatus.TODO
        self.repo.save(task)

        self.audit.record(
            action="task.branch_activate",
            resource_type="task",
            resource_id=str(task.id),
            user_id=actor.id,
            old_value={"active_task_ids": [item.id for item in previously_active]},
            new_value={
                "active_task_id": task.id,
                "branch_label": task.branch_label,
                "reason": data.reason.strip(),
            },
            ip_address=ip_address,
        )
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(
            task.project_id, invalidate_task_ids={item.id for item in siblings}
        )
        return self.repo.get_by_id(task.id) or task

    def _clear_task_restrict_refs(self, task_id: int) -> None:
        """Detach RESTRICT references so the task row can be hard-deleted."""
        from sqlalchemy import update

        from app.models.planning import BranchGroup

        self.db.execute(
            update(BranchGroup)
            .where(BranchGroup.entry_task_id == task_id)
            .values(entry_task_id=None)
        )
        self.db.execute(
            update(BranchGroup)
            .where(BranchGroup.exit_task_id == task_id)
            .values(exit_task_id=None)
        )
        self.db.flush()

    def delete_task(
        self,
        task_id: int,
        data: TaskDeleteRequest,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> None:
        task = self.get_task(task_id)
        project = task.project
        if project is None:
            raise ProjectNotFoundError
        if not can_modify_task_core(actor, task, project, self.db):
            raise PermissionDeniedError("只有项目负责人或管理员可以删除任务")

        old_snapshot = self.audit.task_to_dict(task)
        old_snapshot["project_code"] = project.project_code
        old_snapshot["project_name"] = project.project_name

        self.audit.record(
            action="task.delete",
            resource_type="task",
            resource_id=str(task.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value={
                "deleted": True,
                "reason": data.reason,
                "project_id": project.id,
            },
            ip_address=ip_address,
        )
        project_id = task.project_id
        self._clear_task_restrict_refs(task.id)
        self.repo.delete(task)

        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(project_id, invalidate_task_ids={task_id})
