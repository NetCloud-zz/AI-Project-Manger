"""Notification outbox delivery.

The outbox row is written inside the transaction that justified it — an applied
change proposal, or a risk event that opened, escalated or closed. This service
is the only consumer: it renders one message per recipient, hands it to the
active channel, and records what actually happened. ``SENT`` means the channel
accepted the message; it never means a person read it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.permissions import can_modify_project
from app.models.change_proposal import ChangeProposal
from app.models.notification import (
    RISK_ESCALATED,
    RISK_EVENT_TYPES,
    RISK_OPENED,
    RISK_RESOLVED,
    NotificationEvent,
)
from app.models.project import Project
from app.models.user import User, UserRole, UserStatus
from app.notifications import get_notification_provider
from app.notifications.provider import NotificationProvider
from app.services.audit import AuditService
from app.services.exceptions import DomainValidationError, PermissionDeniedError

logger = get_logger(__name__)

QUEUED = "QUEUED"
SENT = "SENT"
FAILED = "FAILED"
ACKNOWLEDGED = "ACKNOWLEDGED"

LEVEL_LABELS = {"AT_RISK": "有风险", "DELAYED": "已延期"}
#: Spelling out fact-versus-prediction in every message, not just in the UI.
RISK_KIND = {
    "OVERDUE": "这是已经发生的事实。",
    "ISSUE": "这是已经登记的问题，不是预测。",
    "FORECAST_DELAY": "这是按当前计划推算的预测，已承诺的目标日期没有改变。",
    "MISSING_DATA": "这是资料缺口：当前数据不足以判断，不等于没有风险。",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _uncertain(exc: BaseException) -> bool:
    """A timeout may still have been delivered; the channel gave no answer."""
    if isinstance(exc, TimeoutError):
        return True
    return any("Timeout" in klass.__name__ for klass in type(exc).__mro__)


class NotificationDeliveryService:
    """Reads the outbox, sends, retries with backoff, and records acknowledgement."""

    def __init__(self, db: Session, notifier: NotificationProvider | None = None) -> None:
        self.db = db
        self.notifier = notifier or get_notification_provider()
        self.audit = AuditService(db)
        self.settings = get_settings()

    # ---------------------------------------------------------------- render

    def render(self, event: NotificationEvent) -> str:
        if event.event_type in RISK_EVENT_TYPES:
            return self._render_risk(event)
        return self._render_plan_change(event)

    def _render_risk(self, event: NotificationEvent) -> str:
        payload = event.payload or {}
        project = f"{payload.get('project_name') or ''}（{payload.get('project_code') or ''}）"
        heading = {
            RISK_OPENED: "风险提醒",
            RISK_ESCALATED: "风险升级",
            RISK_RESOLVED: "风险解除",
        }[event.event_type]
        lines = [f"【{heading}】{project.strip('（）')}", payload.get("title") or ""]
        # Say which kind of statement this is before saying anything else about it.
        kind = RISK_KIND.get(str(payload.get("risk_type")))
        if kind:
            lines.append(kind)
        if event.event_type == RISK_ESCALATED:
            before = payload.get("previous_level")
            if before and before != payload.get("level"):
                lines.append(
                    f"级别变化：{LEVEL_LABELS.get(str(before), '')}"
                    f" → {LEVEL_LABELS.get(str(payload.get('level')), '')}"
                )
            else:
                lines.append(f"这条风险仍未关闭，影响已扩大到 {payload.get('impact_days')} 天。")
        if event.event_type == RISK_RESOLVED:
            lines.append(f"关闭依据：{payload.get('resolution') or '检测条件不再成立'}")
        else:
            if payload.get("cause"):
                lines.append(f"判断依据：{payload['cause']}")
            if payload.get("impact_date"):
                label = "预测完成" if payload.get("is_prediction") else "涉及日期"
                delay = payload.get("impact_days")
                suffix = f"（晚 {delay} 天）" if delay else ""
                lines.append(f"{label}：{payload['impact_date']}{suffix}")
            lines.append("本条由确定性规则触发，不是模型判断；如与实际不符请在页面上关闭并说明。")
        base = self.settings.frontend_base_url.rstrip("/")
        lines.append(f"详情：{base}/projects/{event.project_id}/risks")
        return "\n".join(line for line in lines if line)

    def _render_plan_change(self, event: NotificationEvent) -> str:
        payload = event.payload or {}
        lines = [
            f"【计划变更】{payload.get('project_name') or ''}"
            f"（{payload.get('project_code') or ''}）".rstrip("（）"),
        ]
        project_diff = payload.get("project")
        if project_diff:
            before = (project_diff.get("before") or {}).get("target_date") or "未设置"
            after = (project_diff.get("after") or {}).get("target_date") or "未设置"
            lines.append(f"项目目标日期：{before} → {after}")
        forecast = payload.get("forecast_finish_date")
        if forecast:
            lines.append(f"预测完成日期：{forecast}")
        tasks = payload.get("tasks") or []
        if tasks:
            lines.append(f"涉及你的任务 {len(tasks)} 项：")
            for task in tasks[:10]:
                if task.get("is_new"):
                    lines.append(
                        f"- 新增 {task.get('task_name')}："
                        f"{task.get('start_date') or '未定'} ~ {task.get('due_date') or '未定'}"
                    )
                else:
                    lines.append(
                        f"- {task.get('task_name')}："
                        f"{task.get('before_due_date') or '未定'}"
                        f" → {task.get('due_date') or '未定'}"
                    )
            if len(tasks) > 10:
                lines.append(f"- 其余 {len(tasks) - 10} 项见详情页")
        if payload.get("reason"):
            lines.append(f"原因：{payload['reason']}")
        if payload.get("operator_name"):
            lines.append(f"操作人：{payload['operator_name']}")
        lines.append("请查看详情并确认知悉。")
        base = self.settings.frontend_base_url.rstrip("/")
        lines.append(f"详情：{base}/notifications")
        return "\n".join(lines)

    # -------------------------------------------------------------- dispatch

    def claim(self, limit: int) -> list[NotificationEvent]:
        now = utc_now()
        query = (
            select(NotificationEvent)
            .where(
                NotificationEvent.status == QUEUED,
                NotificationEvent.next_attempt_at <= now,
            )
            .order_by(NotificationEvent.next_attempt_at, NotificationEvent.id)
            .limit(limit)
        )
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            # Parallel workers must not send the same row twice.
            query = query.with_for_update(skip_locked=True)
        return list(self.db.scalars(query))

    def dispatch_pending(self, limit: int | None = None) -> dict[str, int]:
        events = self.claim(limit or self.settings.NOTIFICATION_DISPATCH_BATCH)
        counts = {"sent": 0, "retry": 0, "failed": 0}
        for event in events:
            outcome = self.deliver(event)
            counts[outcome] = counts.get(outcome, 0) + 1
        return counts

    def deliver(self, event: NotificationEvent) -> str:
        event.attempts += 1
        recipient = self.db.get(User, event.recipient_id)
        if recipient is None or recipient.status != UserStatus.ACTIVE:
            return self._fail(event, "收件人不存在或已停用，需人工处理后补发")
        if not self.notifier.can_reach(event.recipient_id):
            return self._fail(event, f"渠道 {self.notifier.name} 没有该用户的接收地址")
        try:
            self.notifier.send_text_message(
                recipient_id=event.recipient_id, message=self.render(event)
            )
        except Exception as exc:  # noqa: BLE001 — channel errors are recorded, not raised
            event.delivery_uncertain = event.delivery_uncertain or _uncertain(exc)
            return self._retry_or_fail(event, f"{type(exc).__name__}: {exc}")
        event.status = SENT
        event.sent_at = utc_now()
        event.last_error = None
        event.next_attempt_at = None
        logger.info(
            "notification.sent",
            event_id=event.id,
            event_type=event.event_type,
            proposal_id=event.proposal_id,
            risk_event_id=event.risk_event_id,
            recipient_id=event.recipient_id,
            channel=self.notifier.name,
            simulated=self.notifier.simulated,
            attempts=event.attempts,
        )
        return "sent"

    def _retry_or_fail(self, event: NotificationEvent, error: str) -> str:
        if event.attempts >= self.settings.NOTIFICATION_MAX_ATTEMPTS:
            return self._fail(event, error)
        delay = self.settings.NOTIFICATION_RETRY_BACKOFF_SECONDS * (2 ** (event.attempts - 1))
        event.status = QUEUED
        event.last_error = error[:2000]
        event.next_attempt_at = utc_now() + timedelta(seconds=min(delay, 3600))
        logger.warning(
            "notification.retry",
            event_id=event.id,
            attempts=event.attempts,
            error=error,
        )
        return "retry"

    def _fail(self, event: NotificationEvent, error: str) -> str:
        event.status = FAILED
        event.last_error = error[:2000]
        event.next_attempt_at = None
        logger.error(
            "notification.failed",
            event_id=event.id,
            recipient_id=event.recipient_id,
            attempts=event.attempts,
            error=error,
        )
        return "failed"

    # ----------------------------------------------------------------- reads

    def view(self, event: NotificationEvent, *, for_recipient: bool) -> dict[str, Any]:
        payload = event.payload or {}
        return {
            "id": event.id,
            "proposal_id": event.proposal_id,
            "project_id": event.project_id,
            "project_code": payload.get("project_code"),
            "project_name": payload.get("project_name"),
            "recipient_id": event.recipient_id,
            "recipient_name": self._name(event.recipient_id),
            "event_type": event.event_type,
            "channel": event.channel,
            "simulated": event.channel == "console",
            "status": event.status,
            "attempts": event.attempts,
            "last_error": event.last_error,
            "delivery_uncertain": event.delivery_uncertain,
            "created_at": _iso(event.created_at),
            "next_attempt_at": _iso(event.next_attempt_at),
            "sent_at": _iso(event.sent_at),
            "acknowledged_at": _iso(event.acknowledged_at),
            "can_acknowledge": for_recipient and event.status in {QUEUED, SENT, FAILED},
            "reason": payload.get("reason"),
            "operator_name": payload.get("operator_name"),
            "project": payload.get("project"),
            "forecast_finish_date": payload.get("forecast_finish_date"),
            "tasks": payload.get("tasks") or [],
            "risk_event_id": event.risk_event_id,
            "risk": self._risk_view(event) if event.event_type in RISK_EVENT_TYPES else None,
        }

    @staticmethod
    def _risk_view(event: NotificationEvent) -> dict[str, Any]:
        payload = event.payload or {}
        return {
            "risk_type": payload.get("risk_type"),
            "level": payload.get("level"),
            "previous_level": payload.get("previous_level"),
            "title": payload.get("title"),
            "cause": payload.get("cause"),
            "task_id": payload.get("task_id"),
            "issue_id": payload.get("issue_id"),
            "impact_date": payload.get("impact_date"),
            "impact_days": payload.get("impact_days"),
            "resolution": payload.get("resolution"),
            "is_prediction": bool(payload.get("is_prediction")),
            "kind_note": RISK_KIND.get(str(payload.get("risk_type"))),
        }

    def _name(self, user_id: int) -> str:
        user = self.db.get(User, user_id)
        return user.name if user else f"#{user_id}"

    def list_for_user(
        self, actor: User, *, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        query = select(NotificationEvent).where(NotificationEvent.recipient_id == actor.id)
        if status:
            query = query.where(NotificationEvent.status == status)
        rows = self.db.scalars(
            query.order_by(NotificationEvent.created_at.desc(), NotificationEvent.id.desc()).limit(
                min(limit, 200)
            )
        )
        return [self.view(row, for_recipient=True) for row in rows]

    def list_for_proposal(
        self, project_id: int, proposal_id: str, actor: User
    ) -> list[dict[str, Any]]:
        project = self.db.get(Project, project_id)
        if project is None:
            raise DomainValidationError("项目不存在")
        proposal = self.db.get(ChangeProposal, proposal_id)
        if proposal is None or proposal.project_id != project_id:
            raise DomainValidationError("变更方案不存在于该项目")
        manager = can_modify_project(actor, project, self.db) or actor.role == UserRole.EXECUTIVE
        rows = list(
            self.db.scalars(
                select(NotificationEvent)
                .where(NotificationEvent.proposal_id == proposal_id)
                .order_by(NotificationEvent.recipient_id)
            )
        )
        if not manager:
            # Without plan-manager rights a user only sees their own delivery row.
            rows = [row for row in rows if row.recipient_id == actor.id]
            if not rows:
                raise PermissionDeniedError()
        return [self.view(row, for_recipient=row.recipient_id == actor.id) for row in rows]

    def status_summary(self, proposal_id: str) -> dict[str, int]:
        rows = self.db.scalars(
            select(NotificationEvent).where(NotificationEvent.proposal_id == proposal_id)
        )
        summary = {"total": 0, QUEUED: 0, SENT: 0, FAILED: 0, ACKNOWLEDGED: 0}
        for row in rows:
            summary["total"] += 1
            summary[row.status] = summary.get(row.status, 0) + 1
        return summary

    # ---------------------------------------------------------------- writes

    def _event(self, event_id: int) -> NotificationEvent:
        event = self.db.get(NotificationEvent, event_id)
        if event is None:
            raise DomainValidationError("通知记录不存在")
        return event

    def acknowledge(self, event_id: int, actor: User) -> dict[str, Any]:
        event = self._event(event_id)
        if event.recipient_id != actor.id:
            raise PermissionDeniedError("只能确认发给本人的通知")
        if event.status == ACKNOWLEDGED:
            return self.view(event, for_recipient=True)
        event.status = ACKNOWLEDGED
        event.acknowledged_at = utc_now()
        event.next_attempt_at = None
        self.db.flush()
        self.audit.record(
            action="notification.acknowledge",
            resource_type="notification_event",
            resource_id=str(event.id),
            user_id=actor.id,
            new_value={"proposal_id": event.proposal_id, "status": ACKNOWLEDGED},
        )
        return self.view(event, for_recipient=True)

    def requeue(self, event_id: int, actor: User) -> dict[str, Any]:
        """Manual resend after a recorded failure."""
        event = self._event(event_id)
        project = self.db.get(Project, event.project_id)
        if project is None or not can_modify_project(actor, project, self.db):
            raise PermissionDeniedError("只有本项目负责人或管理员可以补发通知")
        if event.status != FAILED:
            raise DomainValidationError("只有失败的通知可以人工补发")
        event.status = QUEUED
        event.attempts = 0
        event.next_attempt_at = utc_now()
        self.db.flush()
        self.audit.record(
            action="notification.requeue",
            resource_type="notification_event",
            resource_id=str(event.id),
            user_id=actor.id,
            old_value={"last_error": event.last_error},
            new_value={"proposal_id": event.proposal_id, "status": QUEUED},
        )
        return self.view(event, for_recipient=event.recipient_id == actor.id)


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


__all__ = [
    "ACKNOWLEDGED",
    "FAILED",
    "QUEUED",
    "SENT",
    "NotificationDeliveryService",
]
