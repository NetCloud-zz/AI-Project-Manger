"""Action item business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.permissions import can_view_issue, can_view_task
from app.models.action_item import ActionItem, ActionItemStatus
from app.models.user import User, UserStatus
from app.repositories.action_item import ActionItemRepository
from app.repositories.issue import IssueRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.schemas.action_item import ActionItemCreate, ActionItemUpdate
from app.services.audit import AuditService
from app.services.exceptions import (
    ActionItemNotFoundError,
    DomainValidationError,
    IssueNotFoundError,
    OwnerNotFoundError,
    PermissionDeniedError,
    TaskNotFoundError,
)

_CLOSED_STATUSES = (ActionItemStatus.DONE, ActionItemStatus.CANCELLED)


class ActionItemService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActionItemRepository(db)
        self.tasks = TaskRepository(db)
        self.issues = IssueRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    def _validate_owner(self, owner_id: int | None) -> None:
        if owner_id is None:
            return
        owner = self.users.get_by_id(owner_id)
        if owner is None or owner.status != UserStatus.ACTIVE:
            raise OwnerNotFoundError

    def _validate_task(self, project_id: int, task_id: int | None, actor: User) -> None:
        if task_id is None:
            return
        task = self.tasks.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError
        if task.project_id != project_id:
            msg = "task_id does not belong to this project"
            raise DomainValidationError(msg)
        if not can_view_task(self.db, actor, task):
            raise PermissionDeniedError("You cannot attach this task")

    def _validate_issue(self, project_id: int, issue_id: int | None, actor: User) -> None:
        if issue_id is None:
            return
        issue = self.issues.get_by_id(issue_id)
        if issue is None:
            raise IssueNotFoundError
        if issue.project_id != project_id:
            msg = "issue_id does not belong to this project"
            raise DomainValidationError(msg)
        if not can_view_issue(self.db, actor, issue):
            raise PermissionDeniedError("You cannot attach this issue")

    def create_action_item(
        self,
        project_id: int,
        data: ActionItemCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> ActionItem:
        self._validate_owner(data.owner_id)
        self._validate_task(project_id, data.task_id, actor)
        self._validate_issue(project_id, data.issue_id, actor)

        item = ActionItem(
            project_id=project_id,
            task_id=data.task_id,
            issue_id=data.issue_id,
            owner_id=data.owner_id,
            created_by=actor.id,
            title=data.title.strip(),
            description=(data.description or "").strip() or None,
            due_date=data.due_date,
            status=data.status,
            priority=data.priority,
        )
        if data.status in _CLOSED_STATUSES:
            item.completed_at = datetime.now(UTC)

        self.repo.add(item)
        self.audit.record(
            action="action_item.create",
            resource_type="action_item",
            resource_id=str(item.id),
            user_id=actor.id,
            new_value=self.audit.action_item_to_dict(item),
            ip_address=ip_address,
        )
        return self.repo.get_by_id(item.id) or item

    def list_action_items(
        self,
        user: User,
        *,
        project_id: int | None = None,
        task_id: int | None = None,
        issue_id: int | None = None,
        owner_id: int | None = None,
        status: ActionItemStatus | None = None,
        open_only: bool = False,
    ) -> list[ActionItem]:
        return self.repo.list_for_user(
            user,
            project_id=project_id,
            task_id=task_id,
            issue_id=issue_id,
            owner_id=owner_id,
            status=status,
            open_only=open_only,
        )

    def get_action_item(self, action_item_id: int) -> ActionItem:
        item = self.repo.get_by_id(action_item_id)
        if item is None:
            raise ActionItemNotFoundError
        return item

    def update_action_item(
        self,
        action_item_id: int,
        data: ActionItemUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> ActionItem:
        item = self.get_action_item(action_item_id)
        old_snapshot = self.audit.action_item_to_dict(item)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            msg = "No action item fields to update"
            raise DomainValidationError(msg)

        if "owner_id" in updates:
            self._validate_owner(updates["owner_id"])
        if "task_id" in updates:
            self._validate_task(item.project_id, updates["task_id"], actor)
        if "issue_id" in updates:
            self._validate_issue(item.project_id, updates["issue_id"], actor)
        if "title" in updates and updates["title"] is not None:
            updates["title"] = updates["title"].strip()
        if "description" in updates and updates["description"] is not None:
            updates["description"] = updates["description"].strip() or None

        old_status = item.status
        if "status" in updates:
            new_status = updates["status"]
            if new_status in _CLOSED_STATUSES and old_status not in _CLOSED_STATUSES:
                item.completed_at = datetime.now(UTC)
            elif new_status not in _CLOSED_STATUSES:
                item.completed_at = None

        for field, value in updates.items():
            setattr(item, field, value)

        self.repo.save(item)
        self.audit.record(
            action="action_item.update",
            resource_type="action_item",
            resource_id=str(item.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value=self.audit.action_item_to_dict(item),
            ip_address=ip_address,
        )
        if "status" in updates and updates["status"] != old_status:
            self.audit.record(
                action="action_item.status_change",
                resource_type="action_item",
                resource_id=str(item.id),
                user_id=actor.id,
                old_value={"status": old_status.value},
                new_value={"status": item.status.value},
                ip_address=ip_address,
            )
        return self.repo.get_by_id(item.id) or item
