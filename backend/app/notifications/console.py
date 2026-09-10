"""Console notification provider — logs messages instead of sending externally."""

from __future__ import annotations

from app.core.logging import get_logger
from app.notifications.provider import (
    NotificationProvider,
    RiskNotificationPayload,
    TaskReminderPayload,
)

logger = get_logger(__name__)


class ConsoleNotificationProvider(NotificationProvider):
    name = "console"
    simulated = True

    def send_text_message(self, *, recipient_id: int, message: str) -> None:
        logger.info(
            "notification.console.text",
            recipient_id=recipient_id,
            message=message,
        )

    def send_task_reminder(self, payload: TaskReminderPayload) -> None:
        logger.info(
            "notification.console.task_reminder",
            task_id=payload.task_id,
            task_name=payload.task_name,
            project_name=payload.project_name,
            owner_id=payload.owner_id,
            owner_name=payload.owner_name,
            due_date=payload.due_date.isoformat() if payload.due_date else None,
            status=payload.status,
        )

    def send_risk_notification(self, payload: RiskNotificationPayload) -> None:
        logger.info(
            "notification.console.risk",
            task_id=payload.task_id,
            task_name=payload.task_name,
            project_name=payload.project_name,
            owner_id=payload.owner_id,
            owner_name=payload.owner_name,
            risk_level=payload.risk_level,
            summary=payload.summary,
        )
