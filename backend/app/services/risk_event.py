"""Deterministic risk detection with a tracked history.

The risk engine keeps a current level on the task and the project. This service
keeps the *record*: what fired, on what evidence, since when, and why it closed.
Every detector here is deterministic — no model is asked whether something is
risky. AI output only enters as evidence the risk engine already accepted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.permissions import can_view_full_project, can_view_task
from app.models.issue import OPEN_ISSUE_STATUSES, Issue, IssueSeverity
from app.models.progress_update import ProgressUpdate
from app.models.project import Project
from app.models.risk_event import (
    RiskEvent,
    RiskEventLevel,
    RiskEventStatus,
    RiskEventType,
)
from app.models.task import Task
from app.models.user import User, UserRole, UserStatus
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.services.risk_notification import (
    RiskNotificationService,
    RiskTransition,
    is_escalation,
)

logger = get_logger(__name__)

#: A task with no progress for this many days is treated as an information gap.
STALE_PROGRESS_DAYS = 2
#: Only chase silence when the deadline is close enough to matter.
STALE_PROGRESS_WINDOW_DAYS = 3


def utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


@dataclass(slots=True)
class Detected:
    """One concrete risk found by one detector in one run."""

    dedupe_key: str
    event_type: RiskEventType
    level: RiskEventLevel
    title: str
    cause: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    task_id: int | None = None
    issue_id: int | None = None
    owner_id: int | None = None
    impact_date: date | None = None
    impact_days: int | None = None


class RiskEventService:
    """Detects, records, closes and reads risk events for one project."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.audit = AuditService(db)

    # ------------------------------------------------------------- detection

    def detect(
        self,
        project: Project,
        *,
        today: date | None = None,
        now: datetime | None = None,
        with_forecast: bool = False,
    ) -> dict[str, int]:
        """Run detectors and reconcile the stored events with what fired.

        ``with_forecast`` runs the schedule engine, which is far more expensive
        than the fact-based detectors. Callers inside a business transaction
        leave it off; the daily scan and explicit refreshes turn it on.
        """
        now = now or utc_now()
        today = today or now.astimezone(ZoneInfo(self.settings.SCHEDULER_TIMEZONE)).date()
        tasks = list(
            self.db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id))
        )

        found: list[Detected] = []
        evaluated = {RiskEventType.OVERDUE, RiskEventType.ISSUE, RiskEventType.MISSING_DATA}
        found.extend(self._overdue(tasks, today=today))
        found.extend(self._issues(project, tasks))
        found.extend(self._missing_data(project, tasks, today=today))
        if with_forecast:
            evaluated.add(RiskEventType.FORECAST_DELAY)
            forecast, forecast_ok = self._forecast(project)
            found.extend(forecast)
            if not forecast_ok:
                # The forecast could not be computed, so its absence proves
                # nothing; leave any existing forecast event alone.
                evaluated.discard(RiskEventType.FORECAST_DELAY)

        return self._reconcile(project, found, evaluated, now=now)

    def _overdue(self, tasks: Iterable[Task], *, today: date) -> list[Detected]:
        results = []
        for task in tasks:
            if not task.is_execution_active or task.due_date is None or task.due_date >= today:
                continue
            late = (today - task.due_date).days
            results.append(
                Detected(
                    dedupe_key=f"OVERDUE:task:{task.id}",
                    event_type=RiskEventType.OVERDUE,
                    level=RiskEventLevel.DELAYED,
                    title=f"任务「{task.task_name}」已逾期 {late} 天",
                    cause=(
                        f"计划截止 {task.due_date.isoformat()}，到 {today.isoformat()} 仍未完成，"
                        f"当前状态 {task.status.value}。这是已发生的事实，不是预测。"
                    ),
                    evidence=[self._task_evidence(task), *self._progress_evidence(task)],
                    task_id=task.id,
                    owner_id=task.owner_id,
                    impact_date=task.due_date,
                    impact_days=late,
                )
            )
        return results

    def _issues(self, project: Project, tasks: Iterable[Task]) -> list[Detected]:
        by_id = {task.id: task for task in tasks}
        rows = self.db.scalars(
            select(Issue)
            .where(
                Issue.project_id == project.id,
                Issue.status.in_(OPEN_ISSUE_STATUSES),
                Issue.severity.in_((IssueSeverity.HIGH, IssueSeverity.CRITICAL)),
            )
            .order_by(Issue.id)
        )
        results = []
        for issue in rows:
            task = by_id.get(issue.task_id) if issue.task_id else None
            if task is not None and not task.is_execution_active:
                # A problem on a shelved branch does not endanger this plan.
                continue
            scope = f"任务「{task.task_name}」" if task else "项目级"
            results.append(
                Detected(
                    dedupe_key=f"ISSUE:issue:{issue.id}",
                    event_type=RiskEventType.ISSUE,
                    level=RiskEventLevel.AT_RISK,
                    title=f"{scope}存在未解决的{issue.severity.value}问题：{issue.title}",
                    cause=(
                        f"问题于 {issue.created_at.date().isoformat()} 登记，"
                        f"当前状态 {issue.status.value}，"
                        f"严重程度 {issue.severity.value}，尚未解决。"
                    ),
                    evidence=[
                        {
                            "source_type": "issue",
                            "source_id": issue.id,
                            "updated_at": _iso(issue.updated_at),
                            "detail": issue.description[:500],
                        },
                        *([self._task_evidence(task)] if task else []),
                    ],
                    task_id=task.id if task else None,
                    issue_id=issue.id,
                    owner_id=(task.owner_id if task else project.owner_id),
                    impact_date=(task.due_date if task else project.target_date),
                )
            )
        return results

    def _missing_data(
        self, project: Project, tasks: Iterable[Task], *, today: date
    ) -> list[Detected]:
        results: list[Detected] = []
        incomplete: list[Task] = []
        for task in tasks:
            if not task.is_execution_active:
                continue
            if task.planned_duration_days is None or task.start_date is None:
                incomplete.append(task)
            if task.due_date is None:
                continue
            silence = self._silent_days(task, today=today)
            due_in = (task.due_date - today).days
            if 0 <= due_in <= STALE_PROGRESS_WINDOW_DAYS and silence >= STALE_PROGRESS_DAYS:
                results.append(
                    Detected(
                        dedupe_key=f"MISSING_DATA:progress:task:{task.id}",
                        event_type=RiskEventType.MISSING_DATA,
                        level=RiskEventLevel.AT_RISK,
                        title=f"任务「{task.task_name}」临近截止但已 {silence} 天无进度",
                        cause=(
                            f"距离 {task.due_date.isoformat()} 截止还有 {due_in} 天，"
                            f"已连续 {silence} 天没有进度更新，无法判断真实状态。"
                        ),
                        evidence=[self._task_evidence(task), *self._progress_evidence(task)],
                        task_id=task.id,
                        owner_id=task.owner_id,
                        impact_date=task.due_date,
                    )
                )
        if incomplete:
            names = "、".join(task.task_name for task in incomplete[:5])
            more = f" 等 {len(incomplete)} 项" if len(incomplete) > 5 else ""
            results.append(
                Detected(
                    dedupe_key="MISSING_DATA:plan:project",
                    event_type=RiskEventType.MISSING_DATA,
                    level=RiskEventLevel.AT_RISK,
                    title=f"{len(incomplete)} 个执行中任务缺少工期或开始日期",
                    cause=(
                        f"{names}{more}没有计划工期或开始日期，交付预测无法覆盖这些任务，"
                        "结果只能视为不确定。"
                    ),
                    evidence=[self._task_evidence(task) for task in incomplete[:20]],
                    owner_id=project.owner_id,
                    impact_date=project.target_date,
                )
            )
        return results

    def _forecast(self, project: Project) -> tuple[list[Detected], bool]:
        """Compare the current-plan prediction with the committed target date.

        Reading the plan requires a manager-level actor; we use the project's
        own owner. If the project has no usable owner we skip rather than
        widen anyone's read scope.
        """
        from app.schemas.scheduling import SchedulePreviewInput
        from app.services.scheduling import SchedulingService

        reader = self._plan_reader(project)
        if reader is None:
            return [], False
        try:
            preview = SchedulingService(self.db).preview(project.id, SchedulePreviewInput(), reader)
        except Exception as exc:  # noqa: BLE001 — a failed forecast is not a risk verdict
            logger.warning("risk.forecast.unavailable", project_id=project.id, error=str(exc))
            return [], False

        current = preview["current"]
        as_of = preview["as_of"]
        finish = current.get("project_finish_date")
        target = project.target_date
        conflicts = current.get("conflicts") or []
        # A target overrun is reported as a conflict but still yields a finish
        # date. Only a missing finish date means the plan cannot be computed.
        if finish is None:
            return (
                [
                    Detected(
                        dedupe_key="MISSING_DATA:forecast:project",
                        event_type=RiskEventType.MISSING_DATA,
                        level=RiskEventLevel.AT_RISK,
                        title="当前计划无法计算交付预测",
                        cause=(
                            "排期引擎没有返回预测完成日期，通常是依赖环、跨项目引用或"
                            "路线数据不一致导致。在这些冲突消除前，任何交付承诺都缺少依据。"
                        ),
                        evidence=[
                            {
                                "source_type": "schedule",
                                "source_id": None,
                                "updated_at": _iso(as_of),
                                "detail": str(item.get("message") or item),
                            }
                            for item in conflicts[:10]
                        ],
                        owner_id=project.owner_id,
                        impact_date=project.target_date,
                    )
                ],
                True,
            )

        if target is None or finish <= target:
            return [], True
        variance = current.get("target_variance_workdays")
        return (
            [
                Detected(
                    dedupe_key="FORECAST_DELAY:project",
                    event_type=RiskEventType.FORECAST_DELAY,
                    # A prediction is not yet a fact, so it never reads DELAYED.
                    level=RiskEventLevel.AT_RISK,
                    title=f"按当前计划预测将于 {finish.isoformat()} 完成，晚于目标日期",
                    cause=(
                        f"以 {_iso(as_of)} 为基准，沿有效依赖图计算的预测完成日期为 "
                        f"{finish.isoformat()}，项目目标日期为 {target.isoformat()}。"
                        "这是预测，不改变已承诺的目标日期。"
                    ),
                    evidence=[
                        {
                            "source_type": "schedule",
                            "source_id": None,
                            "updated_at": _iso(as_of),
                            "detail": (
                                f"预测完成 {finish.isoformat()}；关键任务 "
                                f"{len(current.get('critical_task_ids') or [])} 项；"
                                f"目标偏差 {variance} 工作日"
                            ),
                        },
                        *[
                            {
                                "source_type": "task",
                                "source_id": task_id,
                                "updated_at": _iso(as_of),
                                "detail": "位于关键路径",
                            }
                            for task_id in (current.get("critical_task_ids") or [])[:10]
                        ],
                    ],
                    owner_id=project.owner_id,
                    impact_date=finish,
                    impact_days=abs(variance) if isinstance(variance, int) else None,
                )
            ],
            True,
        )

    def _plan_reader(self, project: Project) -> User | None:
        owner = self.db.get(User, project.owner_id) if project.owner_id else None
        if owner is not None and owner.status == UserStatus.ACTIVE:
            return owner
        return self.db.scalar(
            select(User)
            .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
            .order_by(User.id)
            .limit(1)
        )

    # -------------------------------------------------------------- evidence

    @staticmethod
    def _task_evidence(task: Task) -> dict[str, Any]:
        return {
            "source_type": "task",
            "source_id": task.id,
            "updated_at": _iso(task.updated_at),
            "detail": (
                f"{task.task_name}｜状态 {task.status.value}｜"
                f"计划 {_iso(task.start_date) or '未定'} ~ {_iso(task.due_date)}"
            ),
        }

    def _progress_evidence(self, task: Task) -> list[dict[str, Any]]:
        latest = self.db.scalar(
            select(ProgressUpdate)
            .where(ProgressUpdate.task_id == task.id)
            .order_by(ProgressUpdate.created_at.desc(), ProgressUpdate.id.desc())
            .limit(1)
        )
        if latest is None:
            return []
        return [
            {
                "source_type": "progress",
                "source_id": latest.id,
                "updated_at": _iso(latest.created_at),
                "detail": (latest.summary or latest.raw_content)[:300],
            }
        ]

    def _silent_days(self, task: Task, *, today: date) -> int:
        latest = self.db.scalar(
            select(ProgressUpdate.created_at)
            .where(ProgressUpdate.task_id == task.id)
            .order_by(ProgressUpdate.created_at.desc())
            .limit(1)
        )
        anchor = latest.date() if latest is not None else task.created_at.date()
        return (today - anchor).days

    # ----------------------------------------------------------- reconciling

    def _reconcile(
        self,
        project: Project,
        found: list[Detected],
        evaluated: set[RiskEventType],
        *,
        now: datetime,
    ) -> dict[str, int]:
        existing = {
            row.dedupe_key: row
            for row in self.db.scalars(select(RiskEvent).where(RiskEvent.project_id == project.id))
        }
        counts = {"opened": 0, "updated": 0, "reopened": 0, "resolved": 0}
        seen: set[str] = set()
        transitions: list[RiskTransition] = []

        for item in found:
            seen.add(item.dedupe_key)
            row = existing.get(item.dedupe_key)
            if row is None:
                fresh = self._create(project, item, now=now)
                self.db.add(fresh)
                counts["opened"] += 1
                transitions.append(RiskTransition(fresh, "opened"))
                continue
            reopened = row.status == RiskEventStatus.RESOLVED
            was, was_days = row.level, row.impact_days
            if reopened:
                row.status = RiskEventStatus.OPEN
                row.resolved_at = None
                row.resolved_by = None
                row.resolution = None
                counts["reopened"] += 1
            else:
                counts["updated"] += 1
            self._apply(row, item, now=now)
            if reopened:
                transitions.append(RiskTransition(row, "opened"))
            elif is_escalation(was, was_days, row.level, row.impact_days):
                transitions.append(RiskTransition(row, "escalated", previous_level=was))

        for key, row in existing.items():
            if key in seen or row.status != RiskEventStatus.OPEN:
                continue
            if row.event_type not in evaluated:
                # This detector did not run, so silence is not evidence.
                continue
            row.status = RiskEventStatus.RESOLVED
            row.resolved_at = now
            row.resolution = "自动关闭：检测条件不再成立"
            counts["resolved"] += 1
            transitions.append(RiskTransition(row, "resolved"))
            self.audit.record(
                action="risk_event.auto_resolve",
                resource_type="risk_event",
                resource_id=str(row.id),
                old_value={"status": RiskEventStatus.OPEN.value},
                new_value={"status": RiskEventStatus.RESOLVED.value, "key": row.dedupe_key},
            )

        self.db.flush()
        # Newly created rows only have an id after the flush above.
        RiskNotificationService(self.db).queue(project, transitions)
        return counts

    def _create(self, project: Project, item: Detected, *, now: datetime) -> RiskEvent:
        row = RiskEvent(
            project_id=project.id,
            dedupe_key=item.dedupe_key,
            event_type=item.event_type,
            status=RiskEventStatus.OPEN,
            first_seen_at=now,
            last_seen_at=now,
        )
        self._apply(row, item, now=now)
        self.audit.record(
            action="risk_event.open",
            resource_type="risk_event",
            resource_id=item.dedupe_key,
            new_value={
                "project_id": project.id,
                "type": item.event_type.value,
                "level": item.level.value,
                "title": item.title,
            },
        )
        return row

    @staticmethod
    def _apply(row: RiskEvent, item: Detected, *, now: datetime) -> None:
        row.event_type = item.event_type
        row.level = item.level
        row.title = item.title
        row.cause = item.cause
        row.evidence = item.evidence
        row.task_id = item.task_id
        row.issue_id = item.issue_id
        row.owner_id = item.owner_id
        row.impact_date = item.impact_date
        row.impact_days = item.impact_days
        row.last_seen_at = now

    # ----------------------------------------------------------------- reads

    def view(self, row: RiskEvent) -> dict[str, Any]:
        owner = self.db.get(User, row.owner_id) if row.owner_id else None
        return {
            "id": row.id,
            "project_id": row.project_id,
            "task_id": row.task_id,
            "issue_id": row.issue_id,
            "event_type": row.event_type.value,
            "level": row.level.value,
            "status": row.status.value,
            "title": row.title,
            "cause": row.cause,
            "evidence": row.evidence or [],
            "impact_date": _iso(row.impact_date),
            "impact_days": row.impact_days,
            "owner_id": row.owner_id,
            "owner_name": owner.name if owner else None,
            "first_seen_at": _iso(row.first_seen_at),
            "last_seen_at": _iso(row.last_seen_at),
            "resolved_at": _iso(row.resolved_at),
            "resolution": row.resolution,
        }

    def list_for_project(
        self, project_id: int, actor: User, *, status: str | None = "OPEN"
    ) -> list[dict[str, Any]]:
        project = self.db.get(Project, project_id)
        if project is None:
            raise ProjectNotFoundError
        query = select(RiskEvent).where(RiskEvent.project_id == project_id)
        if status:
            query = query.where(RiskEvent.status == RiskEventStatus(status))
        # Level and status are stored as text; rank them here, not alphabetically.
        rows = sorted(
            self.db.scalars(query),
            key=lambda row: (
                row.status != RiskEventStatus.OPEN,
                row.level != RiskEventLevel.DELAYED,
                row.id,
            ),
        )
        if not can_view_full_project(self.db, actor, project):
            rows = [row for row in rows if self._visible_to(row, actor)]
        return [self.view(row) for row in rows]

    def _visible_to(self, row: RiskEvent, actor: User) -> bool:
        """Without full project access a user only sees risks on their own tasks."""
        if row.task_id is None:
            return False
        task = self.db.get(Task, row.task_id)
        return task is not None and can_view_task(self.db, actor, task)

    # ---------------------------------------------------------------- writes

    def resolve(self, event_id: int, actor: User, note: str) -> dict[str, Any]:
        row = self.db.get(RiskEvent, event_id)
        if row is None:
            raise DomainValidationError("风险记录不存在")
        project = self.db.get(Project, row.project_id)
        if project is None or not can_view_full_project(self.db, actor, project):
            raise PermissionDeniedError("只有本项目负责人、管理员或管理层可以关闭风险记录")
        if len(note.strip()) < 2:
            raise DomainValidationError("请说明关闭依据")
        if row.status == RiskEventStatus.RESOLVED:
            return self.view(row)
        row.status = RiskEventStatus.RESOLVED
        row.resolved_at = utc_now()
        row.resolved_by = actor.id
        row.resolution = note.strip()[:2000]
        self.db.flush()
        RiskNotificationService(self.db).queue(project, [RiskTransition(row, "resolved")])
        self.audit.record(
            action="risk_event.resolve",
            resource_type="risk_event",
            resource_id=str(row.id),
            user_id=actor.id,
            new_value={"resolution": row.resolution, "key": row.dedupe_key},
        )
        return self.view(row)


def open_risk_summary(db: Session, project_id: int) -> dict[str, int]:
    """Counts by type for dashboards and agent context."""
    rows = db.scalars(
        select(RiskEvent).where(
            RiskEvent.project_id == project_id, RiskEvent.status == RiskEventStatus.OPEN
        )
    )
    summary = {"total": 0, **{item.value: 0 for item in RiskEventType}}
    for row in rows:
        summary["total"] += 1
        summary[row.event_type.value] += 1
    return summary


__all__ = [
    "Detected",
    "RiskEventService",
    "open_risk_summary",
]
