"""Scheduled tracking scans executed by Celery Beat."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.notifications import get_notification_provider
from app.notifications.provider import NotificationProvider, TaskReminderPayload
from app.repositories.progress_update import ProgressUpdateRepository
from app.repositories.task import TaskRepository
from app.workers.timezone import day_bounds, scheduler_today

logger = get_logger(__name__)


class ScheduledTrackingService:
    def __init__(
        self,
        db: Session,
        notifier: NotificationProvider | None = None,
    ) -> None:
        self.db = db
        self.tasks = TaskRepository(db)
        self.progress = ProgressUpdateRepository(db)
        self.notifier = notifier or get_notification_provider()

    def scan_daily_tasks(self, *, today: date | None = None) -> int:
        """Remind owners to submit progress for active tasks."""
        today = today or scheduler_today()
        active_tasks = self.tasks.list_active_tasks()
        sent = 0
        for task in active_tasks:
            owner = task.owner
            project = task.project
            if owner is None:
                continue
            self.notifier.send_task_reminder(
                TaskReminderPayload(
                    task_id=task.id,
                    task_name=task.task_name,
                    project_name=project.project_name if project else "",
                    owner_id=owner.id,
                    owner_name=owner.name,
                    due_date=task.due_date,
                    status=task.status.value,
                )
            )
            sent += 1
        logger.info(
            "worker.scan_daily_tasks.completed",
            today=today.isoformat(),
            reminders_sent=sent,
        )
        return sent

    def scan_missing_progress(self, *, today: date | None = None) -> int:
        """Notify owners who have not submitted progress today for active tasks."""
        today = today or scheduler_today()
        start, end = day_bounds(today)
        active_tasks = self.tasks.list_active_tasks()
        sent = 0
        for task in active_tasks:
            owner = task.owner
            project = task.project
            if owner is None:
                continue
            submitted = self.progress.list_task_ids_with_owner_progress_between(
                [task.id],
                owner_id=owner.id,
                start=start,
                end=end,
            )
            if task.id in submitted:
                continue
            message = (
                f"任务「{task.task_name}」今日尚未提交进度更新，"
                f"所属项目：{project.project_name if project else '未知'}，"
                f"截止日期：{task.due_date.isoformat() if task.due_date else '未定'}。"
            )
            self.notifier.send_text_message(recipient_id=owner.id, message=message)
            sent += 1
        logger.info(
            "worker.scan_missing_progress.completed",
            today=today.isoformat(),
            notifications_sent=sent,
        )
        return sent
