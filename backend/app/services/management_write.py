"""Agent writes reuse REST business services, permissions, validation and audit."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.owner_labels import is_pending_owner_label
from app.core.permissions import (
    can_create_action_item,
    can_create_issue,
    can_create_project,
    can_create_task,
    can_modify_action_item,
    can_modify_issue,
    can_modify_project,
    can_modify_task_core,
    can_modify_task_status,
)
from app.models.action_item import ActionItemPriority, ActionItemStatus
from app.models.issue import IssueSeverity, IssueStatus
from app.models.project import Project, ProjectRiskLevel, ProjectStatus
from app.models.task import TaskStatus
from app.models.user import User, UserStatus
from app.repositories.user import UserRepository
from app.schemas.action_item import ActionItemCreate, ActionItemUpdate
from app.schemas.issue import IssueCreate, IssueUpdate
from app.schemas.project import ProjectCreate, ProjectScheduleUpdate, ProjectUpdate
from app.schemas.task import (
    TaskBranchActivate,
    TaskBranchCreate,
    TaskCreate,
    TaskPlanningFields,
    TaskUpdate,
)
from app.services.action_item import ActionItemService
from app.services.exceptions import (
    DomainValidationError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectCodeExistsError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.issue import IssueService
from app.services.management_query import (
    action_item_payload,
    issue_payload,
    project_payload,
    task_payload,
)
from app.services.project import ProjectService
from app.services.task import TaskService

_OWNER_KEYS = ("owner_id", "owner_username", "owner_name")


def _parse_date(value: object | None, *, field: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            msg = f"Invalid {field}: expected YYYY-MM-DD"
            raise DomainValidationError(msg) from exc
    msg = f"Invalid {field}: expected YYYY-MM-DD"
    raise DomainValidationError(msg)


def _has_owner_hint(args: dict[str, Any]) -> bool:
    if args.get("owner_id") is not None:
        return True
    for key in ("owner_username", "owner_name"):
        value = args.get(key)
        if value is None or value == "":
            continue
        if key == "owner_name" and is_pending_owner_label(str(value)):
            continue
        return True
    return False


def _optional_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ManagementWriteService:
    """Agent-facing mutations — always go through domain services + RBAC."""

    def __init__(self, db: Session, *, auto_commit: bool = True) -> None:
        self.db = db
        self.auto_commit = auto_commit
        self.projects = ProjectService(db)
        self.tasks = TaskService(db)
        self.issues = IssueService(db)
        self.action_items = ActionItemService(db)
        self.users = UserRepository(db)

    def _commit(self) -> None:
        if self.auto_commit:
            self.db.commit()
        else:
            self.db.flush()

    def find_users(
        self,
        *,
        query: str | None = None,
        names: list[str] | None = None,
        limit: int = 20,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        if names:
            return self._find_users_by_names(names)
        stmt = select(User).where(User.status == UserStatus.ACTIVE).order_by(User.id)
        if query:
            needle = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(User.name.ilike(needle), User.username.ilike(needle), User.email.ilike(needle))
            )
        users = list(self.db.scalars(stmt.limit(max(1, min(limit, 50)))).all())
        return [
            {
                "id": user.id,
                "name": user.name,
                "username": user.username,
                "role": user.role.value,
                "department": user.department,
            }
            for user in users
        ]

    def _find_users_by_names(self, names: list[str]) -> dict[str, Any]:
        requested: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = str(raw or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            requested.append(name)
        if not requested:
            return {"resolved": [], "ambiguous": [], "not_found": []}
        users = list(
            self.db.scalars(
                select(User).where(User.status == UserStatus.ACTIVE, User.name.in_(requested))
            ).all()
        )
        by_name: dict[str, list[User]] = {}
        for user in users:
            by_name.setdefault(user.name, []).append(user)
        resolved: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        not_found: list[str] = []
        for name in requested:
            matches = by_name.get(name) or []
            if len(matches) == 1:
                user = matches[0]
                resolved.append(
                    {
                        "input": name,
                        "id": user.id,
                        "user_id": user.id,
                        "name": user.name,
                        "username": user.username,
                        "department": user.department,
                    }
                )
            elif len(matches) > 1:
                ambiguous.append(
                    {
                        "input": name,
                        "candidates": [
                            {
                                "id": user.id,
                                "user_id": user.id,
                                "name": user.name,
                                "username": user.username,
                            }
                            for user in matches[:8]
                        ],
                    }
                )
            else:
                not_found.append(name)
        return {"resolved": resolved, "ambiguous": ambiguous, "not_found": not_found}

    def resolve_user(
        self,
        *,
        owner_id: int | None = None,
        owner_username: str | None = None,
        owner_name: str | None = None,
    ) -> User:
        if owner_id is not None:
            user = self.users.get_by_id(int(owner_id))
            if user is None or user.status != UserStatus.ACTIVE:
                raise OwnerNotFoundError
            return user
        if owner_username:
            user = self.users.get_by_username(owner_username.strip())
            if user is None or user.status != UserStatus.ACTIVE:
                raise OwnerNotFoundError
            return user
        if owner_name:
            needle = owner_name.strip()
            matches = list(
                self.db.scalars(
                    select(User).where(
                        User.status == UserStatus.ACTIVE,
                        or_(User.name == needle, User.name.ilike(f"%{needle}%")),
                    )
                ).all()
            )
            exact = [user for user in matches if user.name == needle]
            pool = exact or matches
            if len(pool) == 1:
                return pool[0]
            if not pool:
                raise OwnerNotFoundError
            from app.services.agent_entities import EntityResolutionError

            msg = (
                "Multiple users match owner_name="
                f"{needle!r}; pass owner_id or owner_username instead. "
                f"candidates="
                f"{[{'id': u.id, 'name': u.name, 'username': u.username} for u in pool[:5]]}"
            )
            raise EntityResolutionError(
                msg,
                candidates=[{"id": u.id, "name": u.name, "username": u.username} for u in pool[:5]],
            )
        msg = "Provide owner_id, owner_username, or owner_name"
        raise DomainValidationError(msg)

    def _resolve_project(
        self,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
    ) -> Project:
        if project_id is not None:
            return self.projects.get_project(int(project_id))
        if project_code:
            return self.projects.get_project_by_code(str(project_code).strip().upper())
        msg = "Provide project_id or project_code"
        raise DomainValidationError(msg)

    def create_project(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        if not can_create_project(actor):
            raise PermissionDeniedError("You cannot create projects")

        code = _optional_str(args, "project_code")
        name = _optional_str(args, "project_name")
        if not code or not name:
            msg = "project_code and project_name are required"
            raise DomainValidationError(msg)

        if any(key in args and args[key] not in (None, "") for key in _OWNER_KEYS):
            owner = self.resolve_user(
                owner_id=args.get("owner_id"),
                owner_username=_optional_str(args, "owner_username"),
                owner_name=_optional_str(args, "owner_name"),
            )
        elif args.get("owner_ids"):
            # The legacy primary owner must come from the explicit owner set.
            # Defaulting to the actor would silently add an unrequested owner.
            owner = self.resolve_user(owner_id=args["owner_ids"][0])
        else:
            owner = actor

        status_raw = _optional_str(args, "status")
        risk_raw = _optional_str(args, "risk_level")
        data = ProjectCreate(
            project_code=code.upper(),
            project_name=name,
            goal=_optional_str(args, "goal"),
            owner_id=owner.id,
            owner_ids=args.get("owner_ids"),
            start_date=_parse_date(args.get("start_date"), field="start_date"),
            target_date=_parse_date(args.get("target_date"), field="target_date"),
            status=ProjectStatus(status_raw) if status_raw else ProjectStatus.ACTIVE,
            risk_level=ProjectRiskLevel(risk_raw) if risk_raw else ProjectRiskLevel.NORMAL,
        )
        try:
            project = self.projects.create_project(data, actor=actor)
        except ProjectCodeExistsError as exc:
            msg = f"Project code already exists: {code.upper()}"
            raise DomainValidationError(msg) from exc
        self._commit()
        self.db.refresh(project)
        return {"ok": True, "action": "create_project", "project": project_payload(project)}

    def update_project(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self._resolve_project(
            project_id=args.get("project_id"),
            project_code=_optional_str(args, "project_code"),
        )
        if not can_modify_project(actor, project):
            raise PermissionDeniedError("You cannot modify this project")

        updates: dict[str, Any] = {}
        if "project_name" in args and args["project_name"] is not None:
            updates["project_name"] = str(args["project_name"]).strip()
        if "goal" in args:
            updates["goal"] = _optional_str(args, "goal")
        if "status" in args and args["status"] is not None:
            updates["status"] = ProjectStatus(str(args["status"]))
        if "risk_level" in args and args["risk_level"] is not None:
            updates["risk_level"] = ProjectRiskLevel(str(args["risk_level"]))

        if any(key in args for key in ("owner_id", "owner_username", "owner_name")):
            owner = self.resolve_user(
                owner_id=args.get("owner_id"),
                owner_username=_optional_str(args, "owner_username"),
                owner_name=_optional_str(args, "owner_name"),
            )
            updates["owner_id"] = owner.id

        if "owner_ids" in args:
            updates["owner_ids"] = args["owner_ids"]
        schedule_fields = {
            key: _parse_date(args[key], field=key)
            for key in ("start_date", "target_date")
            if key in args
        }
        schedule = (
            ProjectScheduleUpdate(**schedule_fields, change_reason=args.get("change_reason", ""))
            if schedule_fields
            else None
        )
        if not updates and schedule is None:
            raise DomainValidationError("No project fields to update")
        # Validate/apply dates before metadata so invalid schedule input cannot change owners.
        if schedule is not None:
            project = self.projects.update_schedule(project.id, schedule, actor=actor)
        if updates:
            project = self.projects.update_project(
                project.id, ProjectUpdate(**updates), actor=actor
            )
        self._commit()
        self.db.refresh(project)
        return {"ok": True, "action": "update_project", "project": project_payload(project)}

    def create_task(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self._resolve_project(
            project_id=args.get("project_id"),
            project_code=_optional_str(args, "project_code"),
        )
        if not can_create_task(actor, project):
            raise PermissionDeniedError("You cannot create tasks in this project")

        task_name = _optional_str(args, "task_name")
        if not task_name:
            msg = "task_name is required"
            raise DomainValidationError(msg)

        due = _parse_date(args.get("due_date"), field="due_date")
        owner_id: int | None = None
        if _has_owner_hint(args):
            owner_id = self.resolve_user(
                owner_id=args.get("owner_id"),
                owner_username=_optional_str(args, "owner_username"),
                owner_name=_optional_str(args, "owner_name"),
            ).id
        status_raw = _optional_str(args, "status")
        data = TaskCreate(
            **{key: args[key] for key in TaskPlanningFields.model_fields if key in args},
            task_name=task_name,
            work_stream=_optional_str(args, "work_stream"),
            owner_id=owner_id,
            due_date=due,
            start_date=_parse_date(args.get("start_date"), field="start_date"),
            progress_percent=args.get("progress_percent"),
            status=TaskStatus(status_raw) if status_raw else TaskStatus.TODO,
        )
        task = self.tasks.create_task(project.id, data, actor=actor)
        self._commit()
        self.db.refresh(task)
        return {"ok": True, "action": "create_task", "task": task_payload(task)}

    def update_task(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        task_id = args.get("task_id")
        if task_id is None:
            msg = "task_id is required"
            raise DomainValidationError(msg)

        try:
            task = self.tasks.get_task(int(task_id))
        except TaskNotFoundError:
            raise
        project = task.project
        if project is None:
            raise ProjectNotFoundError

        if not can_modify_task_status(actor, task, project):
            raise PermissionDeniedError("You cannot modify this task")

        updates: dict[str, Any] = {
            key: args[key] for key in TaskPlanningFields.model_fields if key in args
        }
        if "task_name" in args and args["task_name"] is not None:
            updates["task_name"] = str(args["task_name"]).strip()
        if "status" in args and args["status"] is not None:
            updates["status"] = TaskStatus(str(args["status"]))
        if "progress_percent" in args and args["progress_percent"] is not None:
            updates["progress_percent"] = int(args["progress_percent"])
        if "work_stream" in args:
            updates["work_stream"] = _optional_str(args, "work_stream")
        if "start_date" in args:
            updates["start_date"] = _parse_date(args.get("start_date"), field="start_date")

        if any(key in args for key in ("owner_id", "owner_username", "owner_name")):
            if _has_owner_hint(args):
                updates["owner_id"] = self.resolve_user(
                    owner_id=args.get("owner_id"),
                    owner_username=_optional_str(args, "owner_username"),
                    owner_name=_optional_str(args, "owner_name"),
                ).id
            else:
                updates["owner_id"] = None

        if "due_date" in args:
            parsed = _parse_date(args.get("due_date"), field="due_date")
            if parsed is None:
                msg = "due_date cannot be empty"
                raise DomainValidationError(msg)
            updates["due_date"] = parsed

        if not updates:
            msg = "No task fields to update"
            raise DomainValidationError(msg)

        allow_core = can_modify_task_core(actor, task, project)
        # Non-core actors (task owners) may only touch status / progress.
        core_keys = {"task_name", "work_stream", "owner_id", "start_date", "due_date"} | set(
            TaskPlanningFields.model_fields
        )
        if not allow_core and core_keys.intersection(updates):
            raise PermissionDeniedError(
                "You can only update status or progress_percent on this task"
            )

        task = self.tasks.update_task(
            task.id,
            TaskUpdate(**updates),
            actor=actor,
            allow_core_fields=allow_core,
            expected_version=(
                int(args["expected_version"]) if args.get("expected_version") is not None else None
            ),
        )
        self._commit()
        self.db.refresh(task)
        return {"ok": True, "action": "update_task", "task": task_payload(task)}

    def assign_task(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "task_id": args.get("task_id"),
            "target_task_name": args.get("target_task_name"),
            "project_id": args.get("project_id"),
            "project_code": args.get("project_code"),
            "owner_id": args.get("owner_id"),
            "owner_name": args.get("owner_name"),
            "owner_username": args.get("owner_username"),
            "expected_version": args.get("expected_version"),
        }
        return self.update_task(actor, payload)

    def change_task_status(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        return self.update_task(
            actor,
            {
                "task_id": args.get("task_id"),
                "target_task_name": args.get("target_task_name"),
                "project_id": args.get("project_id"),
                "project_code": args.get("project_code"),
                "status": args.get("status"),
                "expected_version": args.get("expected_version"),
            },
        )

    def reschedule_task(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": args.get("task_id"),
            "target_task_name": args.get("target_task_name"),
            "project_id": args.get("project_id"),
            "project_code": args.get("project_code"),
            "expected_version": args.get("expected_version"),
        }
        if args.get("due_date") is not None:
            payload["due_date"] = args.get("due_date")
        if args.get("start_date") is not None:
            payload["start_date"] = args.get("start_date")
        if args.get("offset_days") is not None:
            task_id = args.get("task_id")
            if task_id is None:
                raise DomainValidationError("reschedule_task with offset_days requires task_id")
            task = self.tasks.get_task(int(task_id))
            from datetime import timedelta

            days = int(args["offset_days"])
            if task.due_date is not None:
                payload["due_date"] = (task.due_date + timedelta(days=days)).isoformat()
            if task.start_date is not None and args.get("shift_start", True):
                payload["start_date"] = (task.start_date + timedelta(days=days)).isoformat()
        return self.update_task(actor, payload)

    def create_task_branch(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        task = self.tasks.get_task(int(args["task_id"]))
        if not can_modify_task_core(actor, task, task.project, self.db):
            raise PermissionDeniedError("You cannot manage branches in this project")
        data = TaskBranchCreate(**{key: value for key, value in args.items() if key != "task_id"})
        branch = self.tasks.create_branch(task.id, data, actor=actor)
        self._commit()
        return {"ok": True, "action": "create_task_branch", "task": task_payload(branch)}

    def activate_task_branch(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        task = self.tasks.get_task(int(args["task_id"]))
        if not can_modify_task_core(actor, task, task.project, self.db):
            raise PermissionDeniedError("You cannot manage branches in this project")
        task = self.tasks.activate_branch(
            task.id, TaskBranchActivate(reason=args.get("reason", "")), actor=actor
        )
        self._commit()
        return {"ok": True, "action": "activate_task_branch", "task": task_payload(task)}

    def create_issue(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self._resolve_project(
            project_id=args.get("project_id"),
            project_code=_optional_str(args, "project_code"),
        )
        if not can_create_issue(self.db, actor, project):
            raise PermissionDeniedError("You cannot log issues in this project")

        title = _optional_str(args, "title")
        description = _optional_str(args, "description")
        if not title or not description:
            msg = "title and description are required"
            raise DomainValidationError(msg)

        severity_raw = _optional_str(args, "severity")
        data = IssueCreate(
            title=title,
            description=description,
            task_id=int(args["task_id"]) if args.get("task_id") is not None else None,
            severity=IssueSeverity(severity_raw) if severity_raw else IssueSeverity.MEDIUM,
        )
        issue = self.issues.create_issue(project.id, data, actor=actor)
        self._commit()
        self.db.refresh(issue)
        return {"ok": True, "action": "create_issue", "issue": issue_payload(issue)}

    def update_issue(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        issue_id = args.get("issue_id")
        if issue_id is None:
            msg = "issue_id is required"
            raise DomainValidationError(msg)

        issue = self.issues.get_issue(int(issue_id))
        if not can_modify_issue(actor, issue):
            raise PermissionDeniedError("You cannot modify this issue")

        updates: dict[str, Any] = {}
        for key in ("title", "description"):
            if key in args and args[key] is not None:
                updates[key] = str(args[key]).strip()
        if args.get("severity") is not None:
            updates["severity"] = IssueSeverity(str(args["severity"]))
        if args.get("status") is not None:
            updates["status"] = IssueStatus(str(args["status"]))

        if not updates:
            msg = "No issue fields to update"
            raise DomainValidationError(msg)

        issue = self.issues.update_issue(issue.id, IssueUpdate(**updates), actor=actor)
        self._commit()
        self.db.refresh(issue)
        return {"ok": True, "action": "update_issue", "issue": issue_payload(issue)}

    def create_action_item(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self._resolve_project(
            project_id=args.get("project_id"),
            project_code=_optional_str(args, "project_code"),
        )
        if not can_create_action_item(self.db, actor, project):
            raise PermissionDeniedError("You cannot create action items in this project")

        title = _optional_str(args, "title")
        if not title:
            msg = "title is required"
            raise DomainValidationError(msg)

        owner_id: int | None = None
        if any(key in args and args[key] not in (None, "") for key in _OWNER_KEYS):
            owner_id = self.resolve_user(
                owner_id=args.get("owner_id"),
                owner_username=_optional_str(args, "owner_username"),
                owner_name=_optional_str(args, "owner_name"),
            ).id

        priority_raw = _optional_str(args, "priority")
        status_raw = _optional_str(args, "status")
        data = ActionItemCreate(
            title=title,
            description=_optional_str(args, "description"),
            owner_id=owner_id,
            task_id=int(args["task_id"]) if args.get("task_id") is not None else None,
            issue_id=int(args["issue_id"]) if args.get("issue_id") is not None else None,
            due_date=_parse_date(args.get("due_date"), field="due_date"),
            status=ActionItemStatus(status_raw) if status_raw else ActionItemStatus.OPEN,
            priority=(
                ActionItemPriority(priority_raw) if priority_raw else ActionItemPriority.MEDIUM
            ),
        )
        item = self.action_items.create_action_item(project.id, data, actor=actor)
        self._commit()
        self.db.refresh(item)
        return {
            "ok": True,
            "action": "create_action_item",
            "action_item": action_item_payload(item),
        }

    def update_action_item(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        action_item_id = args.get("action_item_id")
        if action_item_id is None:
            msg = "action_item_id is required"
            raise DomainValidationError(msg)

        item = self.action_items.get_action_item(int(action_item_id))
        if not can_modify_action_item(actor, item, item.project):
            raise PermissionDeniedError("You cannot modify this action item")

        updates: dict[str, Any] = {}
        if args.get("title") is not None:
            updates["title"] = str(args["title"]).strip()
        if "description" in args:
            updates["description"] = _optional_str(args, "description")
        if args.get("status") is not None:
            updates["status"] = ActionItemStatus(str(args["status"]))
        if args.get("priority") is not None:
            updates["priority"] = ActionItemPriority(str(args["priority"]))
        if "task_id" in args:
            updates["task_id"] = int(args["task_id"]) if args.get("task_id") is not None else None
        if "issue_id" in args:
            updates["issue_id"] = (
                int(args["issue_id"]) if args.get("issue_id") is not None else None
            )
        if any(key in args for key in _OWNER_KEYS):
            updates["owner_id"] = self.resolve_user(
                owner_id=args.get("owner_id"),
                owner_username=_optional_str(args, "owner_username"),
                owner_name=_optional_str(args, "owner_name"),
            ).id

        # Same field permission as the REST action-item editor.
        if "due_date" in args:
            updates["due_date"] = _parse_date(args.get("due_date"), field="due_date")

        if not updates:
            msg = "No action item fields to update"
            raise DomainValidationError(msg)

        item = self.action_items.update_action_item(
            item.id, ActionItemUpdate(**updates), actor=actor
        )
        self._commit()
        self.db.refresh(item)
        return {
            "ok": True,
            "action": "update_action_item",
            "action_item": action_item_payload(item),
        }
