"""Deterministic rules for items requiring executive / management intervention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.permissions import can_view_full_project
from app.models.issue import Issue, IssueSeverity
from app.models.project import Project, ProjectRiskLevel
from app.models.task import TaskAiStatus
from app.models.user import User
from app.repositories.issue import IssueRepository
from app.repositories.progress_update import ProgressUpdateRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.schemas.dashboard import ManagementAttentionItem
from app.services.risk_engine import days_without_progress

HIGH_OPEN_STALE_DAYS = 7
STALE_PROGRESS_ATTENTION_DAYS = 3


@dataclass(frozen=True, slots=True)
class _ProjectBrief:
    project_id: int
    project_code: str
    project_name: str


class ManagementAttentionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)
        self.issues = IssueRepository(db)
        self.progress = ProgressUpdateRepository(db)

    def get_management_attention_items(
        self,
        user: User,
        *,
        today: date | None = None,
        now: datetime | None = None,
    ) -> list[ManagementAttentionItem]:
        today = today or datetime.now(UTC).date()
        now = now or datetime.now(UTC)
        visible_projects = [
            project
            for project in self.projects.list_for_user(user)
            if can_view_full_project(self.db, user, project)
        ]
        if not visible_projects:
            return []

        project_ids = [project.id for project in visible_projects]
        project_map = {
            project.id: _ProjectBrief(
                project_id=project.id,
                project_code=project.project_code,
                project_name=project.project_name,
            )
            for project in visible_projects
        }

        items: list[ManagementAttentionItem] = []
        items.extend(self._critical_open_issues(project_ids, project_map))
        items.extend(self._high_open_stale_issues(project_ids, project_map, now=now))
        items.extend(self._severely_delayed_tasks(project_ids, project_map, today=today))
        items.extend(self._stale_progress_tasks(project_ids, project_map, today=today))
        items.extend(self._delayed_projects(visible_projects))
        return items

    def _critical_open_issues(
        self,
        project_ids: list[int],
        project_map: dict[int, _ProjectBrief],
    ) -> list[ManagementAttentionItem]:
        issues = self.issues.list_open_by_project_ids(
            project_ids,
            severities=(IssueSeverity.CRITICAL,),
        )
        return [self._issue_item(issue, project_map, "ISSUE_CRITICAL") for issue in issues]

    def _high_open_stale_issues(
        self,
        project_ids: list[int],
        project_map: dict[int, _ProjectBrief],
        *,
        now: datetime,
    ) -> list[ManagementAttentionItem]:
        cutoff = now - timedelta(days=HIGH_OPEN_STALE_DAYS)
        issues = self.issues.list_open_by_project_ids(
            project_ids,
            severities=(IssueSeverity.HIGH,),
            created_before=cutoff,
        )
        return [self._issue_item(issue, project_map, "ISSUE_HIGH_STALE") for issue in issues]

    def _severely_delayed_tasks(
        self,
        project_ids: list[int],
        project_map: dict[int, _ProjectBrief],
        *,
        today: date,
    ) -> list[ManagementAttentionItem]:
        tasks = self.tasks.list_active_by_project_ids(project_ids)
        items: list[ManagementAttentionItem] = []
        for task_list in tasks.values():
            for task in task_list:
                if task.due_date is None or (
                    today <= task.due_date and task.ai_status != TaskAiStatus.DELAYED
                ):
                    continue
                brief = project_map[task.project_id]
                items.append(
                    ManagementAttentionItem(
                        item_type="TASK_DELAYED",
                        project_id=brief.project_id,
                        project_code=brief.project_code,
                        project_name=brief.project_name,
                        summary=f"任务「{task.task_name}」已严重延期",
                        resource_type="task",
                        resource_id=task.id,
                    )
                )
        return items

    def _stale_progress_tasks(
        self,
        project_ids: list[int],
        project_map: dict[int, _ProjectBrief],
        *,
        today: date,
    ) -> list[ManagementAttentionItem]:
        tasks_by_project = self.tasks.list_active_by_project_ids(project_ids)
        all_task_ids = [task.id for task_list in tasks_by_project.values() for task in task_list]
        latest_progress = self.progress.latest_created_at_by_task_ids(all_task_ids)

        items: list[ManagementAttentionItem] = []
        for task_list in tasks_by_project.values():
            for task in task_list:
                stale_days = days_without_progress(
                    latest_progress.get(task.id),
                    today=today,
                    fallback_date=task.created_at.date(),
                )
                if stale_days < STALE_PROGRESS_ATTENTION_DAYS:
                    continue
                brief = project_map[task.project_id]
                items.append(
                    ManagementAttentionItem(
                        item_type="TASK_STALE_PROGRESS",
                        project_id=brief.project_id,
                        project_code=brief.project_code,
                        project_name=brief.project_name,
                        summary=(f"任务「{task.task_name}」已连续 {stale_days} 天未提交进度"),
                        resource_type="task",
                        resource_id=task.id,
                    )
                )
        return items

    def _delayed_projects(self, projects: list[Project]) -> list[ManagementAttentionItem]:
        items: list[ManagementAttentionItem] = []
        for project in projects:
            if project.risk_level != ProjectRiskLevel.DELAYED:
                continue
            items.append(
                ManagementAttentionItem(
                    item_type="PROJECT_DELAYED",
                    project_id=project.id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    summary=f"项目「{project.project_name}」处于延期状态",
                    resource_type="project",
                    resource_id=project.id,
                )
            )
        return items

    @staticmethod
    def _issue_item(
        issue: Issue,
        project_map: dict[int, _ProjectBrief],
        item_type: str,
    ) -> ManagementAttentionItem:
        brief = project_map[issue.project_id]
        return ManagementAttentionItem(
            item_type=item_type,
            project_id=brief.project_id,
            project_code=brief.project_code,
            project_name=brief.project_name,
            summary=f"Issue「{issue.title}」({issue.severity.value})",
            resource_type="issue",
            resource_id=issue.id,
        )
