"""WeCom notification provider."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.integrations.wecom.client import WeComClient
from app.integrations.wecom.exceptions import WeComNotConfiguredError
from app.models.user import User
from app.notifications.provider import (
    NotificationProvider,
    RiskNotificationPayload,
    TaskReminderPayload,
)

logger = get_logger(__name__)


class WeComNotificationProvider(NotificationProvider):
    name = "wecom"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: WeComClient | None = None,
        db_factory: Callable[[], Session] | None = None,
        close_sessions: bool = True,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client or WeComClient(self._settings)
        self._db_factory: Callable[[], Session] = db_factory or SessionLocal
        self._close_sessions = close_sessions

    def _resolve_wechat_user_id(self, recipient_id: int) -> str | None:
        db = self._db_factory()
        try:
            user = db.get(User, recipient_id)
            if user is None:
                logger.warning("wecom.notification.user_not_found", recipient_id=recipient_id)
                return None
            return user.wechat_user_id
        finally:
            if self._close_sessions:
                db.close()

    def _frontend_url(self, path: str) -> str:
        base = self._settings.frontend_base_url.rstrip("/")
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{base}{normalized}"

    def can_reach(self, recipient_id: int) -> bool:
        return bool(self._resolve_wechat_user_id(recipient_id))

    def _send_to_user(self, *, recipient_id: int, content: str) -> None:
        if not self._settings.wecom_configured:
            raise WeComNotConfiguredError("WeCom credentials are not configured")
        wechat_user_id = self._resolve_wechat_user_id(recipient_id)
        if not wechat_user_id:
            logger.warning(
                "wecom.notification.skip_unmapped_user",
                recipient_id=recipient_id,
            )
            return
        self._client.send_text_message(wechat_user_id=wechat_user_id, content=content)

    def send_text_message(self, *, recipient_id: int, message: str) -> None:
        self._send_to_user(recipient_id=recipient_id, content=message)

    def send_task_reminder(self, payload: TaskReminderPayload) -> None:
        due_label = payload.due_date.strftime("%m-%d")
        update_url = self._frontend_url(f"/tasks/{payload.task_id}/update")
        content = (
            f"{payload.project_name}\n"
            f"任务：{payload.task_name}\n"
            f"截止：{due_label}\n"
            "今天有什么进展？\n"
            f"更新进度：{update_url}"
        )
        self._send_to_user(recipient_id=payload.owner_id, content=content)

    def send_risk_notification(self, payload: RiskNotificationPayload) -> None:
        task_url = self._frontend_url(f"/tasks/{payload.task_id}")
        content = (
            f"【风险提醒】{payload.risk_level}\n"
            f"项目：{payload.project_name}\n"
            f"任务：{payload.task_name}\n"
            f"说明：{payload.summary}\n"
            f"查看详情：{task_url}"
        )
        self._send_to_user(recipient_id=payload.owner_id, content=content)
