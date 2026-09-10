"""Deterministic risk evaluation — program rules take precedence over LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.issue import IssueSeverity
from app.models.progress_update import ProgressUpdate
from app.models.project import Project, ProjectRiskLevel
from app.models.task import Task, TaskAiStatus
from app.notifications import get_notification_provider
from app.notifications.provider import NotificationProvider, RiskNotificationPayload
from app.repositories.issue import IssueRepository
from app.repositories.progress_update import ProgressUpdateRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.services.audit import AuditService
from app.services.risk_event import RiskEventService

_STATUS_PRIORITY: dict[TaskAiStatus, int] = {
    TaskAiStatus.ON_TRACK: 0,
    TaskAiStatus.AT_RISK: 1,
    TaskAiStatus.DELAYED: 2,
}

_RISK_LEVEL_PRIORITY: dict[ProjectRiskLevel, int] = {
    ProjectRiskLevel.NORMAL: 0,
    ProjectRiskLevel.AT_RISK: 1,
    ProjectRiskLevel.DELAYED: 2,
}


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    tasks_updated: int = 0
    projects_updated: int = 0
    notifications_sent: int = 0


def merge_ai_status(
    rule_status: TaskAiStatus | None,
    llm_status: TaskAiStatus | None,
) -> TaskAiStatus | None:
    """Merge rule and LLM statuses; ON_TRACK never downgrades a higher rule status."""
    candidates = [status for status in (rule_status, llm_status) if status is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda status: _STATUS_PRIORITY[status])


def days_without_progress(
    last_progress_at: datetime | None,
    *,
    today: date,
    fallback_date: date,
) -> int:
    anchor = last_progress_at.date() if last_progress_at is not None else fallback_date
    return (today - anchor).days


class RiskEngine:
    def __init__(
        self,
        db: Session,
        notifier: NotificationProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.tasks = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.progress = ProgressUpdateRepository(db)
        self.issues = IssueRepository(db)
        self.audit = AuditService(db)
        self.notifier = notifier or get_notification_provider()

    def evaluate_all(
        self,
        *,
        today: date | None = None,
        now: datetime | None = None,
        send_notifications: bool = True,
    ) -> RiskEvaluationResult:
        today = (
            today
            or (now or datetime.now(UTC))
            .astimezone(ZoneInfo(self.settings.SCHEDULER_TIMEZONE))
            .date()
        )
        now = now or datetime.now(UTC)
        tasks_updated = 0
        notifications_sent = 0
        project_ids = {project.id for project in self.projects.list_all()}

        for task in self.tasks.list_active_tasks():
            changed, sent = self.evaluate_task(
                task,
                today=today,
                now=now,
                send_notifications=send_notifications,
            )
            if changed:
                tasks_updated += 1
            notifications_sent += sent
            project_ids.add(task.project_id)

        projects_updated = 0
        events = RiskEventService(self.db)
        for project_id in project_ids:
            project = self.projects.get_by_id(project_id)
            if project is None:
                continue
            if self.evaluate_project(project):
                projects_updated += 1
            # The daily pass is the one place that can afford the forecast.
            events.detect(project, today=today, now=now, with_forecast=True)

        return RiskEvaluationResult(
            tasks_updated=tasks_updated,
            projects_updated=projects_updated,
            notifications_sent=notifications_sent,
        )

    def evaluate_task(
        self,
        task: Task,
        *,
        today: date | None = None,
        now: datetime | None = None,
        llm_status: TaskAiStatus | None = None,
        send_notifications: bool = True,
    ) -> tuple[bool, int]:
        if not task.is_execution_active:
            return False, 0

        today = (
            today
            or (now or datetime.now(UTC))
            .astimezone(ZoneInfo(self.settings.SCHEDULER_TIMEZONE))
            .date()
        )
        now = now or datetime.now(UTC)
        last_progress = self._latest_progress_at(task.id)
        rule_status = self._compute_rule_status(task, today=today, last_progress_at=last_progress)
        # Never feed the previously merged task.ai_status back as LLM evidence.
        evidence = self._current_llm_status(task, now=now)
        final_status = merge_ai_status(
            rule_status, llm_status if llm_status is not None else evidence
        )

        notifications_sent = 0
        if send_notifications:
            notifications_sent = self._send_stale_progress_notifications(
                task,
                today=today,
                last_progress_at=last_progress,
            )

        changed = False
        if task.ai_risk_level != rule_status:
            old_risk = task.ai_risk_level.value if task.ai_risk_level else None
            task.ai_risk_level = rule_status
            changed = True
            self.audit.record(
                action="task.ai_risk_level_change",
                resource_type="task",
                resource_id=str(task.id),
                old_value={"ai_risk_level": old_risk},
                new_value={"ai_risk_level": rule_status.value},
            )

        if final_status != task.ai_status:
            old_status = task.ai_status.value if task.ai_status else None
            task.ai_status = final_status
            changed = True
            self.audit.record(
                action="task.ai_status_change",
                resource_type="task",
                resource_id=str(task.id),
                old_value={"ai_status": old_status},
                new_value={"ai_status": final_status.value if final_status else None},
            )

        if changed:
            self.tasks.save(task)
        return changed, notifications_sent

    def evaluate_project(self, project: Project) -> bool:
        tasks = self.tasks.list_by_project(project.id)
        active_tasks = [task for task in tasks if task.is_execution_active]
        new_level = self._compute_project_risk(active_tasks)
        # Project-level issues remain relevant even when there are no active tasks.
        project_issues = self.issues.list_open_by_project_ids(
            [project.id], severities=(IssueSeverity.HIGH, IssueSeverity.CRITICAL)
        )
        if any(issue.task_id is None for issue in project_issues):
            new_level = max(
                (new_level, ProjectRiskLevel.AT_RISK), key=lambda level: _RISK_LEVEL_PRIORITY[level]
            )
        if project.risk_level == new_level:
            return False

        old_level = project.risk_level.value
        project.risk_level = new_level
        self.projects.save(project)
        self.audit.record(
            action="project.risk_level_change",
            resource_type="project",
            resource_id=str(project.id),
            old_value={"risk_level": old_level},
            new_value={"risk_level": new_level.value},
        )
        return True

    def refresh_project(
        self,
        project_id: int,
        *,
        invalidate_task_ids: set[int] | None = None,
        with_forecast: bool = False,
    ) -> None:
        """Recompute after a business mutation in the caller's transaction; no notifications."""
        now = datetime.now(UTC)
        tasks = self.tasks.list_by_project(project_id)
        for task in tasks:
            if invalidate_task_ids and task.id in invalidate_task_ids:
                task.risk_context_changed_at = now
            self.evaluate_task(task, now=now, send_notifications=False)
        project = self.projects.get_by_id(project_id)
        if project is not None:
            self.evaluate_project(project)
            # Fact-based detectors are cheap; the forecast runs the schedule
            # engine and is left to the daily scan and explicit refreshes.
            RiskEventService(self.db).detect(project, now=now, with_forecast=with_forecast)
        self.db.flush()

    def _current_llm_status(self, task: Task, *, now: datetime) -> TaskAiStatus | None:
        updates = self.progress.list_by_task(task.id, limit=1)
        if not updates:
            return None
        latest = updates[0]
        return latest.ai_status if self.is_current_evidence(task, latest, now=now) else None

    def is_current_evidence(
        self,
        task: Task,
        progress: ProgressUpdate,
        *,
        now: datetime | None = None,
    ) -> bool:
        """A late worker may preserve history but must not revive superseded risks/issues."""
        updates = self.progress.list_by_task(task.id, limit=1)
        if not updates or updates[0].id != progress.id:
            return False
        latest = progress
        now = now or datetime.now(UTC)
        if latest.ai_analysis_failed or latest.ai_status is None:
            return False
        submitted = self._utc(latest.created_at)
        if submitted > self._utc(now) or self._utc(now) - submitted > timedelta(
            days=self.settings.AI_RISK_EVIDENCE_MAX_AGE_DAYS
        ):
            return False
        return not (
            task.risk_context_changed_at is not None
            and submitted <= self._utc(task.risk_context_changed_at)
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _compute_rule_status(
        self,
        task: Task,
        *,
        today: date,
        last_progress_at: datetime | None,
    ) -> TaskAiStatus:
        if task.due_date is not None and today > task.due_date:
            return TaskAiStatus.DELAYED

        status = TaskAiStatus.ON_TRACK

        if self.issues.list_open_high_severity_by_task(task.id):
            status = TaskAiStatus.AT_RISK

        if task.due_date is None:
            return status

        days_until_due = (task.due_date - today).days
        if days_until_due <= 3:
            stale_days = days_without_progress(
                last_progress_at,
                today=today,
                fallback_date=task.created_at.date(),
            )
            if stale_days >= 2:
                status = max([status, TaskAiStatus.AT_RISK], key=lambda s: _STATUS_PRIORITY[s])

        return status

    def _compute_project_risk(self, tasks: list[Task]) -> ProjectRiskLevel:
        statuses = [task.ai_status for task in tasks if task.ai_status is not None]
        if any(status == TaskAiStatus.DELAYED for status in statuses):
            return ProjectRiskLevel.DELAYED
        if any(status == TaskAiStatus.AT_RISK for status in statuses):
            return ProjectRiskLevel.AT_RISK
        return ProjectRiskLevel.NORMAL

    def _latest_progress_at(self, task_id: int) -> datetime | None:
        updates = self.progress.list_by_task(task_id, limit=1)
        return updates[0].created_at if updates else None

    def _send_stale_progress_notifications(
        self,
        task: Task,
        *,
        today: date,
        last_progress_at: datetime | None,
    ) -> int:
        owner = task.owner
        project = task.project
        if owner is None:
            return 0

        stale_days = days_without_progress(
            last_progress_at,
            today=today,
            fallback_date=task.created_at.date(),
        )
        sent = 0
        if stale_days >= 2:
            self.notifier.send_risk_notification(
                RiskNotificationPayload(
                    task_id=task.id,
                    task_name=task.task_name,
                    project_name=project.project_name if project else "",
                    owner_id=owner.id,
                    owner_name=owner.name,
                    risk_level="STALE_PROGRESS",
                    summary=f"任务已连续 {stale_days} 天未提交进度更新",
                )
            )
            sent += 1

        if stale_days >= 3 and project is not None and project.owner_id != owner.id:
            project_owner = project.owner
            if project_owner is not None:
                self.notifier.send_risk_notification(
                    RiskNotificationPayload(
                        task_id=task.id,
                        task_name=task.task_name,
                        project_name=project.project_name,
                        owner_id=project_owner.id,
                        owner_name=project_owner.name,
                        risk_level="STALE_PROGRESS",
                        summary=(
                            f"任务「{task.task_name}」已连续 {stale_days} 天未提交进度，"
                            f"负责人：{owner.name}"
                        ),
                    )
                )
                sent += 1
        return sent
