"""Daily project summary business logic."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.agents.daily_summary_generator import (
    DailySummaryFacts,
    DailySummaryGenerator,
    DailySummaryResult,
)
from app.models.daily_project_summary import DailyProjectSummary
from app.models.issue import IssueSeverity
from app.models.project import Project, ProjectStatus
from app.repositories.daily_summary import DailySummaryRepository
from app.repositories.issue import IssueRepository
from app.repositories.progress_update import ProgressUpdateRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.services.audit import AuditService
from app.services.exceptions import ProjectNotFoundError
from app.services.management_attention import ManagementAttentionService
from app.workers.timezone import day_bounds


class DailySummaryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)
        self.issues = IssueRepository(db)
        self.progress = ProgressUpdateRepository(db)
        self.repo = DailySummaryRepository(db)
        self.audit = AuditService(db)
        self.generator = DailySummaryGenerator()

    def list_summaries(self, project_id: int, *, limit: int = 30) -> list[DailyProjectSummary]:
        self._require_project(project_id)
        return self.repo.list_by_project(project_id, limit=limit)

    def get_latest_summary(self, project_id: int) -> DailyProjectSummary | None:
        self._require_project(project_id)
        return self.repo.get_latest(project_id)

    async def generate_for_project(
        self,
        project_id: int,
        *,
        summary_date: date | None = None,
        skip_if_exists: bool = True,
    ) -> DailyProjectSummary | None:
        project = self.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError
        summary_date = summary_date or date.today()

        if skip_if_exists:
            existing = self.repo.get_by_project_and_date(project_id, summary_date)
            if existing is not None:
                return existing

        facts = self._collect_facts(project, summary_date)
        result = await self.generator.generate(facts)
        return self._persist_summary(project_id, summary_date, result)

    async def generate_all_active(
        self,
        *,
        summary_date: date | None = None,
    ) -> int:
        """Generate summaries for all ACTIVE projects; returns count created/updated."""
        summary_date = summary_date or date.today()
        projects = self.projects.list_by_status(ProjectStatus.ACTIVE)
        count = 0
        for project in projects:
            row = await self.generate_for_project(
                project.id,
                summary_date=summary_date,
                skip_if_exists=True,
            )
            if row is not None:
                count += 1
        return count

    def _collect_facts(self, project: Project, summary_date: date) -> DailySummaryFacts:
        start_utc, end_utc = day_bounds(summary_date)
        tasks = self.tasks.list_by_project(project.id)
        active_tasks = [task for task in tasks if task.is_execution_active]

        today_progress: list[str] = []
        for progress in self.progress.list_recent_by_project(project.id, limit=50):
            created_at = _as_utc_aware(progress.created_at)
            if created_at >= start_utc and created_at < end_utc:
                task_name = progress.task.task_name if progress.task else "?"
                today_progress.append(f"{task_name}: {progress.raw_content}")

        open_issues = self.issues.list_open_by_project_ids([project.id])
        issue_lines = [
            f"[{issue.severity.value}] {issue.title} ({issue.status.value})"
            for issue in open_issues
        ]
        critical_count = sum(1 for issue in open_issues if issue.severity == IssueSeverity.CRITICAL)

        task_snapshots = [
            (
                f"{task.task_name}: status={task.status.value}, "
                f"due={task.due_date.isoformat() if task.due_date else 'unset'}, "
                f"ai_status={task.ai_status.value if task.ai_status else 'UNKNOWN'}"
            )
            for task in active_tasks
        ]

        mgmt_items = ManagementAttentionService(self.db).get_management_attention_items(
            project.owner,
            today=summary_date,
        )
        project_mgmt = [item for item in mgmt_items if item.project_id == project.id]
        mgmt_required = len(project_mgmt) > 0
        mgmt_reasons = [item.summary for item in project_mgmt]

        return DailySummaryFacts(
            project_code=project.project_code,
            project_name=project.project_name,
            project_goal=project.goal,
            project_status=project.status.value,
            project_risk_level=project.risk_level.value,
            target_date=project.target_date.isoformat() if project.target_date else None,
            summary_date=summary_date,
            today_progress_entries=today_progress,
            open_issues=issue_lines,
            critical_issue_count=critical_count,
            task_snapshots=task_snapshots,
            management_attention_required=mgmt_required,
            management_attention_reasons=mgmt_reasons,
        )

    def _persist_summary(
        self,
        project_id: int,
        summary_date: date,
        result: DailySummaryResult,
    ) -> DailyProjectSummary:
        existing = self.repo.get_by_project_and_date(project_id, summary_date)
        if existing is not None:
            existing.summary = result.summary
            existing.risk_summary = result.risk_summary
            existing.next_action = result.next_action
            existing.management_attention = result.management_attention
            self.repo.add(existing)
            row = existing
        else:
            row = DailyProjectSummary(
                project_id=project_id,
                summary_date=summary_date,
                summary=result.summary,
                risk_summary=result.risk_summary,
                next_action=result.next_action,
                management_attention=result.management_attention,
            )
            self.repo.add(row)

        self.audit.record(
            action="daily_summary.generate",
            resource_type="daily_project_summary",
            resource_id=str(row.id),
            user_id=None,
            new_value={
                "project_id": project_id,
                "summary_date": summary_date.isoformat(),
                "overall_status": result.overall_status,
            },
        )
        return row

    def _require_project(self, project_id: int) -> Project:
        project = self.projects.get_by_id(project_id)
        if project is None:
            raise ProjectNotFoundError
        return project


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
