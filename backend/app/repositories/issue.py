"""Issue data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.issue import OPEN_ISSUE_STATUSES, Issue, IssueSeverity, IssueStatus
from app.models.project import project_owners
from app.models.user import User, UserRole


class IssueRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, issue_id: int) -> Issue | None:
        return self.db.scalar(
            select(Issue)
            .options(
                joinedload(Issue.reporter),
                joinedload(Issue.task),
                joinedload(Issue.project),
            )
            .where(Issue.id == issue_id)
        )

    def list_for_user(
        self,
        user: User,
        *,
        project_id: int | None = None,
        task_id: int | None = None,
        status: IssueStatus | None = None,
        open_only: bool = False,
    ) -> list[Issue]:
        from app.models.task import Task

        stmt = (
            select(Issue)
            .options(
                joinedload(Issue.reporter),
                joinedload(Issue.task),
                joinedload(Issue.project),
            )
            .order_by(desc(Issue.created_at), desc(Issue.id))
        )
        if project_id is not None:
            stmt = stmt.where(Issue.project_id == project_id)
        if task_id is not None:
            stmt = stmt.where(Issue.task_id == task_id)
        if status is not None:
            stmt = stmt.where(Issue.status == status)
        elif open_only:
            stmt = stmt.where(Issue.status.in_(OPEN_ISSUE_STATUSES))

        if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
            return list(self.db.scalars(stmt).unique().all())
        if user.role == UserRole.PROJECT_OWNER:
            co_owned = select(project_owners.c.project_id).where(
                project_owners.c.user_id == user.id
            )
            stmt = stmt.where(
                or_(Issue.project.has(owner_id=user.id), Issue.project_id.in_(co_owned))
            )
            return list(self.db.scalars(stmt).unique().all())

        # Members see issues on their own tasks, ones they reported, and
        # project-level issues in projects where they hold a task.
        member_projects = select(Task.project_id).where(Task.owner_id == user.id)
        stmt = stmt.where(
            or_(
                Issue.task.has(Task.owner_id == user.id),
                Issue.reported_by == user.id,
                Issue.project_id.in_(member_projects),
            )
        )
        return list(self.db.scalars(stmt).unique().all())

    def list_open_by_task(self, task_id: int) -> list[Issue]:
        stmt = (
            select(Issue)
            .where(
                Issue.task_id == task_id,
                Issue.status.in_((IssueStatus.OPEN, IssueStatus.IN_PROGRESS)),
            )
            .order_by(desc(Issue.created_at))
        )
        return list(self.db.scalars(stmt).all())

    def list_open_by_project_ids(
        self,
        project_ids: list[int],
        *,
        severities: tuple[IssueSeverity, ...] | None = None,
        created_before: datetime | None = None,
    ) -> list[Issue]:
        if not project_ids:
            return []
        stmt = select(Issue).where(
            Issue.project_id.in_(project_ids),
            Issue.status.in_((IssueStatus.OPEN, IssueStatus.IN_PROGRESS)),
        )
        if severities is not None:
            stmt = stmt.where(Issue.severity.in_(severities))
        if created_before is not None:
            stmt = stmt.where(Issue.created_at < created_before)
        stmt = stmt.order_by(desc(Issue.created_at), desc(Issue.id))
        return list(self.db.scalars(stmt).all())

    def list_open_high_severity_by_task(self, task_id: int) -> list[Issue]:
        from app.models.issue import IssueSeverity

        stmt = select(Issue).where(
            Issue.task_id == task_id,
            Issue.status.in_((IssueStatus.OPEN, IssueStatus.IN_PROGRESS)),
            Issue.severity.in_((IssueSeverity.HIGH, IssueSeverity.CRITICAL)),
        )
        return list(self.db.scalars(stmt).all())

    def add(self, issue: Issue) -> Issue:
        self.db.add(issue)
        self.db.flush()
        return issue

    def save(self, issue: Issue) -> Issue:
        self.db.add(issue)
        self.db.flush()
        return issue
