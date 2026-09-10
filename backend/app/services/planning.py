"""S1 planning editors with project-scoped validation and caller-owned transactions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.core.permissions import can_modify_project, can_view_project, can_view_task
from app.models.planning import (
    BranchGroup,
    BranchOption,
    Milestone,
    PlanVersion,
    ProjectMember,
    TaskGroup,
    TaskParticipant,
    WorkCalendar,
)
from app.models.project import Project
from app.models.task import Task, TaskLink, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.planning import (
    BranchGroupInput,
    BranchOptionInput,
    BranchSelectInput,
    CalendarInput,
    MemberInput,
    MilestoneInput,
    ParticipantsInput,
    PlanVersionInput,
    TaskGroupInput,
)
from app.schemas.task import TaskResponse
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
)


def record(row: Any) -> dict[str, Any]:
    result = {}
    for column in inspect(type(row)).columns:
        value = getattr(row, column.key)
        result[column.key] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return result


class PlanningService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    def project(
        self, project_id: int, actor: User, *, write: bool = False, full: bool = False
    ) -> Project:
        # Lock the project on writes to serialize version/selection mutations.
        query = select(Project).where(Project.id == project_id)
        if write:
            query = query.with_for_update()
        project = self.db.scalar(query)
        if project is None:
            raise ProjectNotFoundError
        manager = can_modify_project(actor, project, self.db)
        if write and not manager or full and not (manager or actor.role == UserRole.EXECUTIVE):
            raise PermissionDeniedError("Only project managers can access this plan operation")
        if not can_view_project(self.db, actor, project):
            raise PermissionDeniedError()
        return project

    def user_name(self, user_id: int) -> str:
        user = self.db.get(User, user_id)
        return user.name if user else f"#{user_id}"

    def user(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise DomainValidationError("User not found or inactive")
        return user

    def scoped(self, model: Any, row_id: int, project_id: int) -> Any:
        row = self.db.get(model, row_id)
        if row is None or row.project_id != project_id:
            raise DomainValidationError("Record does not belong to this project")
        return row

    def save(
        self,
        row: Any,
        actor: User,
        action: str,
        *,
        old: dict | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.db.add(row)
        self.db.flush()
        payload = record(row)
        self.audit.record(
            action=action,
            resource_type=row.__tablename__,
            resource_id=str(getattr(row, "id", getattr(row, "project_id", ""))),
            user_id=actor.id,
            old_value=old,
            new_value={**payload, **({"reason": reason} if reason else {})},
        )
        return payload

    def rows(self, model: Any, project_id: int) -> list[Any]:
        return list(self.db.scalars(select(model).where(model.project_id == project_id)).all())

    def context(self, project_id: int, actor: User) -> dict[str, Any]:
        project = self.project(project_id, actor)
        full = can_modify_project(actor, project, self.db) or actor.role == UserRole.EXECUTIVE
        tasks = [
            task for task in self.rows(Task, project_id) if can_view_task(self.db, actor, task)
        ]
        groups = self.rows(BranchGroup, project_id) if full else []
        options = (
            list(
                self.db.scalars(
                    select(BranchOption).where(BranchOption.group_id.in_([g.id for g in groups]))
                )
            )
            if groups
            else []
        )
        versions = self.rows(PlanVersion, project_id) if full else []
        calendar = self.db.get(WorkCalendar, project_id)
        visible_ids = {task.id for task in tasks}
        return {
            "project_id": project_id,
            "editable": can_modify_project(actor, project, self.db),
            "full_access": full,
            "calendar": record(calendar)
            if calendar
            else {
                "project_id": project_id,
                "name": "项目工作日历",
                "timezone": "Asia/Shanghai",
                "weekdays": [0, 1, 2, 3, 4],
                "exceptions": {},
                "version": 0,
            },
            "members": [
                {**record(member), "user_name": self.user_name(member.user_id)}
                for member in self.rows(ProjectMember, project_id)
                if full or member.user_id == actor.id
            ],
            "tasks": [TaskResponse.model_validate(task).model_dump(mode="json") for task in tasks],
            "milestones": [record(row) for row in self.rows(Milestone, project_id)] if full else [],
            "task_groups": [record(row) for row in self.rows(TaskGroup, project_id)]
            if full
            else [],
            "branch_groups": [record(row) for row in groups],
            "branch_options": [
                {**record(row), "task_ids": [t.id for t in tasks if t.branch_option_id == row.id]}
                for row in options
            ],
            "links": [
                record(link)
                for link in self.rows(TaskLink, project_id)
                if link.source_id in visible_ids and link.target_id in visible_ids
            ],
            "versions": [
                {key: value for key, value in record(v).items() if key != "snapshot"}
                for v in sorted(versions, key=lambda v: v.version, reverse=True)
            ],
        }

    def put_member(self, project_id: int, user_id: int, data: MemberInput, actor: User) -> dict:
        self.project(project_id, actor, write=True)
        self.user(user_id)
        member = self.db.get(ProjectMember, (project_id, user_id))
        old = record(member) if member else None
        if member is None:
            member = ProjectMember(project_id=project_id, user_id=user_id)
        for key, value in data.model_dump().items():
            setattr(member, key, value)
        return self.save(member, actor, "project.member_update", old=old)

    def participants(self, task_id: int, actor: User) -> list[dict]:
        task = self.db.get(Task, task_id)
        if task is None or not can_view_task(self.db, actor, task):
            raise PermissionDeniedError()
        rows = self.db.scalars(select(TaskParticipant).where(TaskParticipant.task_id == task_id))
        return [{**record(row), "user_name": self.user_name(row.user_id)} for row in rows]

    def put_participants(
        self, project_id: int, task_id: int, data: ParticipantsInput, actor: User
    ) -> list[dict]:
        self.project(project_id, actor, write=True)
        self.scoped(Task, task_id, project_id)
        for person in data.participants:
            self.user(person.user_id)
            member = self.db.get(ProjectMember, (project_id, person.user_id))
            if member is None or not member.is_active:
                raise DomainValidationError("Task participants must be active project members")
        old = self.participants(task_id, actor)
        self.db.execute(delete(TaskParticipant).where(TaskParticipant.task_id == task_id))
        for person in data.participants:
            self.db.add(TaskParticipant(task_id=task_id, **person.model_dump()))
        self.db.flush()
        new = self.participants(task_id, actor)
        self.audit.record(
            action="task.participants_update",
            resource_type="task",
            resource_id=str(task_id),
            user_id=actor.id,
            old_value={"participants": old},
            new_value={"participants": new},
        )
        return new

    def put_calendar(self, project_id: int, data: CalendarInput, actor: User) -> dict:
        self.project(project_id, actor, write=True)
        calendar = self.db.get(WorkCalendar, project_id)
        version = calendar.version if calendar else 0
        if version != data.expected_version:
            raise DomainValidationError("Calendar changed; reload before saving")
        old = record(calendar) if calendar else None
        if calendar is None:
            calendar = WorkCalendar(project_id=project_id)
        values = data.model_dump(mode="json", exclude={"reason", "expected_version"})
        for key, value in values.items():
            setattr(calendar, key, value)
        calendar.version = version + 1
        return self.save(calendar, actor, "project.calendar_update", old=old, reason=data.reason)

    def put_milestone(
        self, project_id: int, data: MilestoneInput, actor: User, row_id: int | None = None
    ) -> dict:
        self.project(project_id, actor, write=True)
        if data.owner_id is not None:
            self.user(data.owner_id)
        row = (
            self.scoped(Milestone, row_id, project_id)
            if row_id
            else Milestone(project_id=project_id)
        )
        old = record(row) if row_id else None
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        return self.save(row, actor, "project.milestone_update", old=old)

    def put_task_group(
        self, project_id: int, data: TaskGroupInput, actor: User, row_id: int | None = None
    ) -> dict:
        self.project(project_id, actor, write=True)
        parent_id = data.parent_id
        seen = {row_id} if row_id else set()
        while parent_id is not None:
            if parent_id in seen:
                raise DomainValidationError("Task group hierarchy must be acyclic")
            seen.add(parent_id)
            parent = self.scoped(TaskGroup, parent_id, project_id)
            parent_id = parent.parent_id
        row = (
            self.scoped(TaskGroup, row_id, project_id)
            if row_id
            else TaskGroup(project_id=project_id)
        )
        old = record(row) if row_id else None
        row.name, row.parent_id = data.name, data.parent_id
        return self.save(row, actor, "project.task_group_update", old=old)

    def create_branch_group(self, project_id: int, data: BranchGroupInput, actor: User) -> dict:
        return self.put_branch_group(project_id, data, actor)

    def put_branch_group(
        self,
        project_id: int,
        data: BranchGroupInput,
        actor: User,
        row_id: int | None = None,
        reason: str | None = None,
    ) -> dict:
        self.project(project_id, actor, write=True)
        if row_id and (not reason or len(reason.strip()) < 2):
            raise DomainValidationError("A meaningful boundary change reason is required")
        if data.entry_task_id is not None and data.entry_task_id == data.exit_task_id:
            raise DomainValidationError("Entry and exit must be different tasks")
        for task_id in (data.entry_task_id, data.exit_task_id):
            if task_id is not None:
                task = self.scoped(Task, task_id, project_id)
                if task.branch_option_id is not None or task.branch_root_id is not None:
                    raise DomainValidationError("Shared entry/exit cannot belong to an alternative")
        row = (
            self.scoped(BranchGroup, row_id, project_id)
            if row_id
            else BranchGroup(project_id=project_id)
        )
        old = record(row) if row_id else None
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        return self.save(
            row,
            actor,
            "project.branch_group_update" if row_id else "project.branch_group_create",
            old=old,
            reason=reason,
        )

    def create_branch_option(
        self, project_id: int, group_id: int, data: BranchOptionInput, actor: User
    ) -> dict:
        self.project(project_id, actor, write=True)
        group = self.scoped(BranchGroup, group_id, project_id)
        if self.db.scalar(
            select(BranchOption.id).where(
                BranchOption.group_id == group_id, BranchOption.name == data.name
            )
        ):
            raise DomainValidationError("Option name already exists")
        tasks = [self.scoped(Task, task_id, project_id) for task_id in data.task_ids]
        shared = {
            value
            for g in self.rows(BranchGroup, project_id)
            for value in (g.entry_task_id, g.exit_task_id)
            if value is not None
        }
        for task in tasks:
            if (
                task.branch_option_id is not None
                or task.branch_root_id is not None
                or task.id in shared
            ):
                raise DomainValidationError("Task already belongs to a branch or is a shared node")
            if task.status != TaskStatus.TODO:
                raise DomainValidationError(
                    "Only not-started tasks can be assigned to a new alternative"
                )
        option = BranchOption(group_id=group.id, name=data.name, is_selected=False)
        self.db.add(option)
        self.db.flush()
        for task in tasks:
            task.branch_option_id = option.id
            task.is_active_branch = False
        payload = self.save(option, actor, "project.branch_option_create", reason=data.reason)
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(project_id, invalidate_task_ids=set(data.task_ids))
        return {**payload, "task_ids": data.task_ids}

    def select_branch(
        self, project_id: int, group_id: int, data: BranchSelectInput, actor: User
    ) -> dict:
        self.project(project_id, actor, write=True)
        self.scoped(BranchGroup, group_id, project_id)
        options = list(
            self.db.scalars(select(BranchOption).where(BranchOption.group_id == group_id))
        )
        selected = [option.id for option in options if option.is_selected]
        if (
            len(selected) > 1
            or (selected[0] if selected else None) != data.expected_selected_option_id
        ):
            raise DomainValidationError("Branch selection changed; reload before selecting")
        if data.option_id not in {option.id for option in options}:
            raise DomainValidationError("Option belongs to another branch group")
        if selected == [data.option_id]:
            return {"selected_option_id": data.option_id}
        tasks = list(
            self.db.scalars(
                select(Task).where(Task.branch_option_id.in_([option.id for option in options]))
            )
        )
        for option in options:
            option.is_selected = option.id == data.option_id
        for task in tasks:
            active = task.branch_option_id == data.option_id
            if (
                not active
                and task.is_active_branch
                and task.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS)
            ):
                task.branch_suspended_status = task.status.value
                task.status = TaskStatus.CANCELLED
            elif active and task.status == TaskStatus.CANCELLED and task.branch_suspended_status:
                # Selection is explicit authorization to resume; never inherit completed work.
                task.status = TaskStatus.IN_PROGRESS if task.actual_start_date else TaskStatus.TODO
                task.branch_suspended_status = None
            task.is_active_branch = active
        self.db.flush()
        self.audit.record(
            action="project.branch_group_select",
            resource_type="branch_group",
            resource_id=str(group_id),
            user_id=actor.id,
            old_value={"selected_option_ids": selected},
            new_value={"selected_option_id": data.option_id, "reason": data.reason},
        )
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(
            project_id, invalidate_task_ids={task.id for task in tasks}
        )
        return {"selected_option_id": data.option_id}

    def capture_version(self, project_id: int, data: PlanVersionInput, actor: User) -> dict:
        project = self.project(project_id, actor, write=True)
        latest = (
            self.db.scalar(
                select(func.max(PlanVersion.version)).where(PlanVersion.project_id == project_id)
            )
            or 0
        )
        if latest != data.expected_latest_version:
            raise DomainValidationError("Plan version changed; reload before capturing")
        context = self.context(project_id, actor)
        context.pop("versions", None)
        snapshot = {
            "project": self.audit.project_to_dict(project),
            **context,
            "participants": [
                record(row)
                for row in self.db.scalars(
                    select(TaskParticipant)
                    .join(Task, Task.id == TaskParticipant.task_id)
                    .where(Task.project_id == project_id)
                )
            ],
        }
        row = PlanVersion(
            project_id=project_id,
            version=latest + 1,
            kind="BASELINE" if latest == 0 else "SNAPSHOT",
            reason=data.reason,
            created_by=actor.id,
            snapshot=snapshot,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.record(
            action="project.plan_capture",
            resource_type="plan_version",
            resource_id=str(row.id),
            user_id=actor.id,
            new_value={"version": row.version, "reason": data.reason},
        )
        return record(row)

    def version(self, project_id: int, version_id: int, actor: User) -> dict:
        self.project(project_id, actor, full=True)
        return record(self.scoped(PlanVersion, version_id, project_id))
