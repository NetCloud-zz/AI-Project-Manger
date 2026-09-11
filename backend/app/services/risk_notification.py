"""Turn risk-event transitions into outbox rows.

A risk that nobody hears about is a risk nobody acts on, so the deterministic
detectors feed the same transactional outbox the change-proposal flow uses:
the intent is written inside the detection transaction and a worker is the only
thing that talks to a channel.

Three deliberate limits keep this from becoming noise:

* Only a **transition** is news. A risk that stays open at the same level for
  three weeks is announced once, not twenty-one times.
* A missing-data finding goes to the people who can fix the data, not to the
  whole project. It says the plan cannot be judged, which is not the same as
  saying the work is late.
* Closure is announced only to people who were told about the risk in the
  first place, so an "all clear" never arrives out of nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.notification import (
    RISK_ESCALATED,
    RISK_OPENED,
    RISK_RESOLVED,
    NotificationEvent,
)
from app.models.planning import ProjectMember
from app.models.project import Project, ProjectStatus
from app.models.risk_event import RiskEvent, RiskEventLevel, RiskEventType
from app.models.user import User, UserStatus

logger = get_logger(__name__)

Transition = Literal["opened", "escalated", "resolved"]

EVENT_TYPES: dict[str, str] = {
    "opened": RISK_OPENED,
    "escalated": RISK_ESCALATED,
    "resolved": RISK_RESOLVED,
}

#: A data gap is a request to the plan owners, not an alarm for the whole team.
OWNERS_ONLY = frozenset({RiskEventType.MISSING_DATA})

CLOSED_STATUSES = frozenset({ProjectStatus.COMPLETED, ProjectStatus.CANCELLED})

#: Day marks at which a risk that is still open is worth saying again. A task
#: one day late and a task a month late are not the same news, but sending a
#: reminder every single day would train people to ignore all of them.
ESCALATION_STEPS = (7, 14, 30)


def _step(days: int | None) -> int:
    return sum(1 for mark in ESCALATION_STEPS if days is not None and days >= mark)


def is_escalation(
    before_level: RiskEventLevel,
    before_days: int | None,
    after_level: RiskEventLevel,
    after_days: int | None,
) -> bool:
    """True when an already-open risk got materially worse."""
    if after_level == RiskEventLevel.DELAYED and before_level != RiskEventLevel.DELAYED:
        return True
    return _step(after_days) > _step(before_days)


@dataclass(slots=True)
class RiskTransition:
    risk: RiskEvent
    kind: Transition
    #: Only set for an escalation, so the message can say what changed.
    previous_level: RiskEventLevel | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskNotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def queue(self, project: Project, transitions: list[RiskTransition]) -> int:
        """Write one outbox row per recipient per newsworthy transition."""
        if not transitions or project.status in CLOSED_STATUSES:
            # A closed project still records risks for the history; nobody needs
            # to be paged about them.
            return 0
        from app.notifications import get_notification_provider

        channel = get_notification_provider().name
        members = {m.user_id: m for m in self._members(project.id)}
        managers = {project.owner_id} | {owner.id for owner in project.owners}
        written = 0
        for transition in transitions:
            recipients = self._recipients(transition, managers, members)
            if not recipients:
                continue
            key = self._next_key(transition.risk)
            payload = self._payload(project, transition)
            for user_id in sorted(recipients):
                self.db.add(
                    NotificationEvent(
                        risk_event_id=transition.risk.id,
                        project_id=project.id,
                        recipient_id=user_id,
                        event_type=EVENT_TYPES[transition.kind],
                        dedupe_key=key,
                        channel=channel,
                        payload=payload,
                        status="QUEUED",
                        attempts=0,
                        next_attempt_at=utc_now(),
                        delivery_uncertain=False,
                    )
                )
                written += 1
        self.db.flush()
        if written:
            logger.info(
                "notification.risk.queued",
                project_id=project.id,
                transitions=len(transitions),
                rows=written,
            )
        return written

    # ------------------------------------------------------------ recipients

    def _members(self, project_id: int) -> list[ProjectMember]:
        return list(
            self.db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id))
        )

    def _recipients(
        self,
        transition: RiskTransition,
        managers: set[int],
        members: dict[int, ProjectMember],
    ) -> set[int]:
        risk = transition.risk
        if transition.kind == "resolved":
            # Only close the loop with people who were opened on it.
            told = set(
                self.db.scalars(
                    select(NotificationEvent.recipient_id).where(
                        NotificationEvent.risk_event_id == risk.id
                    )
                )
            )
            return {user_id for user_id in told if self._reachable(user_id, members)}
        candidates = set(managers)
        if risk.event_type not in OWNERS_ONLY and risk.owner_id:
            candidates.add(risk.owner_id)
        return {user_id for user_id in candidates if self._reachable(user_id, members)}

    def _reachable(self, user_id: int | None, members: dict[int, ProjectMember]) -> bool:
        if user_id is None:
            return False
        user = self.db.get(User, user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            return False
        member = members.get(user_id)
        return not (member and not member.receive_notifications)

    # --------------------------------------------------------------- content

    def _next_key(self, risk: RiskEvent) -> str:
        """A new key per transition; the same transition is never queued twice."""
        seen = (
            self.db.scalar(
                select(func.count(func.distinct(NotificationEvent.dedupe_key))).where(
                    NotificationEvent.risk_event_id == risk.id
                )
            )
            or 0
        )
        return f"RISK:{risk.id}:{seen + 1}"

    @staticmethod
    def _payload(project: Project, transition: RiskTransition) -> dict[str, Any]:
        risk = transition.risk
        return {
            "risk_event_id": risk.id,
            "transition": transition.kind,
            "project_id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "risk_type": risk.event_type.value,
            "level": risk.level.value,
            "previous_level": (
                transition.previous_level.value if transition.previous_level else None
            ),
            "title": risk.title,
            "cause": risk.cause,
            "task_id": risk.task_id,
            "issue_id": risk.issue_id,
            "impact_date": risk.impact_date.isoformat() if risk.impact_date else None,
            "impact_days": risk.impact_days,
            "first_seen_at": risk.first_seen_at.isoformat() if risk.first_seen_at else None,
            "resolution": risk.resolution,
            # Facts and predictions are labelled here so the message never has
            # to guess which one it is holding.
            "is_prediction": risk.event_type == RiskEventType.FORECAST_DELAY,
            "evidence_count": len(risk.evidence or []),
        }


__all__ = ["RiskNotificationService", "RiskTransition"]
