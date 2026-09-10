"""Issue business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.progress_analyzer import ProgressIssue
from app.core.permissions import can_view_task
from app.models.issue import Issue, IssueSeverity, IssueStatus
from app.models.user import User
from app.repositories.issue import IssueRepository
from app.repositories.task import TaskRepository
from app.schemas.issue import IssueCreate, IssueUpdate
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    IssueNotFoundError,
    PermissionDeniedError,
    TaskNotFoundError,
)


def normalize_issue_title(title: str) -> str:
    """Normalize issue titles for deduplication."""
    return " ".join(title.strip().lower().split())


class IssueService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IssueRepository(db)
        self.tasks = TaskRepository(db)
        self.audit = AuditService(db)

    def create_from_progress_analysis(
        self,
        *,
        task_id: int,
        reported_by: int,
        issue: ProgressIssue,
        suggested_solution: str | None = None,
        ip_address: str | None = None,
    ) -> Issue | None:
        """Create an issue from analyzer output; skip when a similar open issue exists."""
        task = self.tasks.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError

        normalized = normalize_issue_title(issue.title)
        for existing in self.repo.list_open_by_task(task_id):
            if normalize_issue_title(existing.title) == normalized:
                return None

        created = Issue(
            project_id=task.project_id,
            task_id=task_id,
            reported_by=reported_by,
            title=issue.title.strip(),
            description=issue.description.strip(),
            severity=IssueSeverity(issue.severity.value),
            status=IssueStatus.OPEN,
            suggested_solution=suggested_solution,
        )
        self.repo.add(created)
        self.audit.record(
            action="issue.create",
            resource_type="issue",
            resource_id=str(created.id),
            user_id=reported_by,
            new_value=self.audit.issue_to_dict(created),
            ip_address=ip_address,
        )
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(created.project_id)
        return self.repo.get_by_id(created.id) or created

    def create_issue(
        self,
        project_id: int,
        data: IssueCreate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Issue:
        """Manually log a problem. ``task_id`` is optional for project-level issues."""
        if data.task_id is not None:
            task = self.tasks.get_by_id(data.task_id)
            if task is None:
                raise TaskNotFoundError
            if task.project_id != project_id:
                msg = "task_id does not belong to this project"
                raise DomainValidationError(msg)
            if not can_view_task(self.db, actor, task):
                raise PermissionDeniedError("You cannot attach an issue to this task")

        created = Issue(
            project_id=project_id,
            task_id=data.task_id,
            reported_by=actor.id,
            title=data.title.strip(),
            description=data.description.strip(),
            severity=data.severity,
            status=data.status,
        )
        if data.status == IssueStatus.RESOLVED:
            created.resolved_at = datetime.now(UTC)

        self.repo.add(created)
        self.audit.record(
            action="issue.create",
            resource_type="issue",
            resource_id=str(created.id),
            user_id=actor.id,
            new_value=self.audit.issue_to_dict(created),
            ip_address=ip_address,
        )
        from app.services.risk_engine import RiskEngine

        RiskEngine(self.db).refresh_project(created.project_id)
        return self.repo.get_by_id(created.id) or created

    def list_issues(
        self,
        user: User,
        *,
        project_id: int | None = None,
        task_id: int | None = None,
        status: IssueStatus | None = None,
        open_only: bool = False,
    ) -> list[Issue]:
        return self.repo.list_for_user(
            user,
            project_id=project_id,
            task_id=task_id,
            status=status,
            open_only=open_only,
        )

    def get_issue(self, issue_id: int) -> Issue:
        issue = self.repo.get_by_id(issue_id)
        if issue is None:
            raise IssueNotFoundError
        return issue

    def update_issue(
        self,
        issue_id: int,
        data: IssueUpdate,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> Issue:
        issue = self.get_issue(issue_id)
        old_snapshot = self.audit.issue_to_dict(issue)
        updates = data.model_dump(exclude_unset=True)

        old_status = issue.status
        old_severity = issue.severity

        if "status" in updates:
            new_status = updates["status"]
            if new_status == IssueStatus.RESOLVED and old_status != IssueStatus.RESOLVED:
                issue.resolved_at = datetime.now(UTC)
            elif new_status != IssueStatus.RESOLVED and old_status == IssueStatus.RESOLVED:
                issue.resolved_at = None

        for field, value in updates.items():
            setattr(issue, field, value)

        self.repo.save(issue)
        new_snapshot = self.audit.issue_to_dict(issue)

        self.audit.record(
            action="issue.update",
            resource_type="issue",
            resource_id=str(issue.id),
            user_id=actor.id,
            old_value=old_snapshot,
            new_value=new_snapshot,
            ip_address=ip_address,
        )
        if "status" in updates and updates["status"] != old_status:
            self.audit.record(
                action="issue.status_change",
                resource_type="issue",
                resource_id=str(issue.id),
                user_id=actor.id,
                old_value={"status": old_status.value},
                new_value={"status": issue.status.value},
                ip_address=ip_address,
            )
        if "severity" in updates and updates["severity"] != old_severity:
            self.audit.record(
                action="issue.severity_change",
                resource_type="issue",
                resource_id=str(issue.id),
                user_id=actor.id,
                old_value={"severity": old_severity.value},
                new_value={"severity": issue.severity.value},
                ip_address=ip_address,
            )
        if issue.status != old_status or issue.severity != old_severity:
            from app.services.risk_engine import RiskEngine

            RiskEngine(self.db).refresh_project(
                issue.project_id, invalidate_task_ids={issue.task_id} if issue.task_id else None
            )
        return self.repo.get_by_id(issue.id) or issue
