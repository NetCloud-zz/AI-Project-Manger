"""Action item data access."""

from __future__ import annotations

from sqlalchemy import Select, desc, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.action_item import (
    OPEN_ACTION_ITEM_STATUSES,
    ActionItem,
    ActionItemStatus,
)
from app.models.project import project_owners
from app.models.task import Task
from app.models.user import User, UserRole


class ActionItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _base_stmt(self) -> Select[tuple[ActionItem]]:
        return (
            select(ActionItem)
            .options(
                joinedload(ActionItem.owner),
                joinedload(ActionItem.creator),
                joinedload(ActionItem.task),
                joinedload(ActionItem.issue),
                joinedload(ActionItem.project),
            )
            .order_by(desc(ActionItem.created_at), desc(ActionItem.id))
        )

    def get_by_id(self, action_item_id: int) -> ActionItem | None:
        return self.db.scalar(self._base_stmt().where(ActionItem.id == action_item_id))

    def list_for_user(
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
        stmt = self._base_stmt()
        if project_id is not None:
            stmt = stmt.where(ActionItem.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(ActionItem.task_id == task_id)
        if issue_id is not None:
            stmt = stmt.where(ActionItem.issue_id == issue_id)
        if owner_id is not None:
            stmt = stmt.where(ActionItem.owner_id == owner_id)
        if status is not None:
            stmt = stmt.where(ActionItem.status == status)
        elif open_only:
            stmt = stmt.where(ActionItem.status.in_(OPEN_ACTION_ITEM_STATUSES))

        if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
            return list(self.db.scalars(stmt).unique().all())
        if user.role == UserRole.PROJECT_OWNER:
            co_owned = select(project_owners.c.project_id).where(
                project_owners.c.user_id == user.id
            )
            stmt = stmt.where(
                or_(ActionItem.project.has(owner_id=user.id), ActionItem.project_id.in_(co_owned))
            )
            return list(self.db.scalars(stmt).unique().all())

        # Members see items they own or created, plus items in projects where they
        # hold a task — a meeting action item is useless if the assignee can't see it.
        member_projects = select(Task.project_id).where(Task.owner_id == user.id)
        stmt = stmt.where(
            or_(
                ActionItem.owner_id == user.id,
                ActionItem.created_by == user.id,
                ActionItem.project_id.in_(member_projects),
            )
        )
        return list(self.db.scalars(stmt).unique().all())

    def list_open_by_project_ids(self, project_ids: list[int]) -> list[ActionItem]:
        if not project_ids:
            return []
        stmt = (
            select(ActionItem)
            .where(
                ActionItem.project_id.in_(project_ids),
                ActionItem.status.in_(OPEN_ACTION_ITEM_STATUSES),
            )
            .order_by(desc(ActionItem.created_at), desc(ActionItem.id))
        )
        return list(self.db.scalars(stmt).all())

    def add(self, item: ActionItem) -> ActionItem:
        self.db.add(item)
        self.db.flush()
        return item

    def save(self, item: ActionItem) -> ActionItem:
        self.db.add(item)
        self.db.flush()
        return item
