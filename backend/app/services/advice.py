"""Advice records: versions, adoption, and whether it actually helped.

Advice that cannot be traced back to evidence, or forward to what someone did
about it, is just text. This service keeps both ends attached.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.solution_advisor import SolutionAdvice
from app.core.permissions import (
    can_request_issue_advice,
    can_view_issue,
)
from app.models.action_item import ActionItem, ActionItemPriority, ActionItemStatus
from app.models.advice_record import AdviceOutcome, AdviceRecord, AdviceStatus
from app.models.issue import Issue, IssueStatus
from app.models.user import User
from app.services.audit import AuditService
from app.services.exceptions import (
    DomainValidationError,
    IssueNotFoundError,
    PermissionDeniedError,
)
from app.services.project_context import ContextBundle

#: An adoption may create at most this many action items in one go.
MAX_ADOPTED_ACTIONS = 20


def utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def context_digest(bundle: ContextBundle) -> str:
    """Fingerprint of the evidence set, so a stale adoption can be spotted."""
    payload = [[item.source_type, item.source_id, item.updated_at] for item in bundle.evidence]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class AdviceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ---------------------------------------------------------- persistence

    def record_generated(
        self,
        issue: Issue,
        advice: SolutionAdvice,
        bundle: ContextBundle,
        *,
        actor_id: int | None,
        model: str | None,
    ) -> AdviceRecord:
        """Store a new version. Earlier undecided versions become SUPERSEDED."""
        previous = list(
            self.db.scalars(
                select(AdviceRecord)
                .where(
                    AdviceRecord.issue_id == issue.id,
                    AdviceRecord.status == AdviceStatus.PROPOSED,
                )
                .order_by(AdviceRecord.version)
            )
        )
        for row in previous:
            row.status = AdviceStatus.SUPERSEDED

        latest = (
            self.db.scalar(
                select(func.max(AdviceRecord.version)).where(AdviceRecord.issue_id == issue.id)
            )
            or 0
        )
        record = AdviceRecord(
            issue_id=issue.id,
            project_id=issue.project_id,
            version=latest + 1,
            status=AdviceStatus.PROPOSED,
            content=advice.model_dump(mode="json"),
            evidence=[
                {
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "updated_at": item.updated_at,
                    "detail": item.detail,
                    "relevance": item.relevance,
                }
                for item in bundle.evidence
            ],
            coverage=bundle.coverage,
            context_digest=context_digest(bundle),
            model=model,
            generated_by=actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self.audit.record(
            action="advice.generate",
            resource_type="advice_record",
            resource_id=str(record.id),
            user_id=actor_id,
            new_value={
                "issue_id": issue.id,
                "version": record.version,
                "evidence_count": len(record.evidence),
                "superseded": [row.id for row in previous],
            },
        )
        return record

    # ---------------------------------------------------------------- reads

    def get(self, advice_id: int, actor: User) -> AdviceRecord:
        record = self.db.get(AdviceRecord, advice_id)
        if record is None:
            raise DomainValidationError("建议记录不存在")
        issue = self.db.get(Issue, record.issue_id)
        if issue is None:
            raise IssueNotFoundError
        if not can_view_issue(self.db, actor, issue):
            raise PermissionDeniedError()
        return record

    def list_for_issue(self, issue_id: int, actor: User) -> list[dict[str, Any]]:
        issue = self.db.get(Issue, issue_id)
        if issue is None:
            raise IssueNotFoundError
        if not can_view_issue(self.db, actor, issue):
            raise PermissionDeniedError()
        rows = self.db.scalars(
            select(AdviceRecord)
            .where(AdviceRecord.issue_id == issue_id)
            .order_by(AdviceRecord.version.desc())
        )
        return [self.view(row) for row in rows]

    def list_for_project(
        self, project_id: int, actor: User, *, status: str | None = None
    ) -> list[dict[str, Any]]:
        query = select(AdviceRecord).where(AdviceRecord.project_id == project_id)
        if status:
            query = query.where(AdviceRecord.status == AdviceStatus(status))
        rows = self.db.scalars(query.order_by(AdviceRecord.id.desc()).limit(200))
        visible = []
        for row in rows:
            issue = self.db.get(Issue, row.issue_id)
            if issue is not None and can_view_issue(self.db, actor, issue):
                visible.append(self.view(row))
        return visible

    def view(self, record: AdviceRecord) -> dict[str, Any]:
        issue = self.db.get(Issue, record.issue_id)
        actions = list(
            self.db.scalars(
                select(ActionItem).where(ActionItem.advice_id == record.id).order_by(ActionItem.id)
            )
        )
        return {
            "id": record.id,
            "issue_id": record.issue_id,
            "issue_title": issue.title if issue else None,
            "issue_status": issue.status.value if issue else None,
            "project_id": record.project_id,
            "version": record.version,
            "status": record.status.value,
            "content": record.content,
            "evidence": record.evidence or [],
            "coverage": record.coverage,
            "context_digest": record.context_digest,
            "model": record.model,
            "generated_by": record.generated_by,
            "generated_at": _iso(record.created_at),
            "decided_by": record.decided_by,
            "decided_at": _iso(record.decided_at),
            "decision_note": record.decision_note,
            "proposal_id": record.proposal_id,
            "outcome": record.outcome.value if record.outcome else None,
            "issue_resolved": record.issue_resolved,
            "outcome_note": record.outcome_note,
            "evaluated_at": _iso(record.evaluated_at),
            "action_items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status.value,
                    "owner_id": item.owner_id,
                    "due_date": _iso(item.due_date),
                }
                for item in actions
            ],
        }

    # --------------------------------------------------------------- writes

    def adopt(
        self,
        advice_id: int,
        actor: User,
        *,
        note: str | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Accept the advice and turn it into owned, dated actions.

        Adoption never touches the plan. If dates must move, the adopter still
        goes through a change proposal; this only records the decision and the
        follow-up work.
        """
        record = self._decidable(advice_id, actor)
        requested = actions or []
        if len(requested) > MAX_ADOPTED_ACTIONS:
            raise DomainValidationError(f"一次最多创建 {MAX_ADOPTED_ACTIONS} 个行动项")

        created = []
        for item in requested:
            title = str(item.get("title", "")).strip()
            if len(title) < 2:
                raise DomainValidationError("行动项标题不能为空")
            owner_id = item.get("owner_id")
            if owner_id is not None and self.db.get(User, owner_id) is None:
                raise DomainValidationError("行动项负责人不存在")
            due = item.get("due_date")
            action = ActionItem(
                project_id=record.project_id,
                issue_id=record.issue_id,
                advice_id=record.id,
                task_id=item.get("task_id"),
                owner_id=owner_id,
                created_by=actor.id,
                title=title[:300],
                description=(item.get("description") or None),
                due_date=date.fromisoformat(due) if isinstance(due, str) else due,
                status=ActionItemStatus.OPEN,
                priority=ActionItemPriority(item.get("priority", "MEDIUM")),
            )
            self.db.add(action)
            created.append(action)

        record.status = AdviceStatus.ADOPTED
        record.decided_by = actor.id
        record.decided_at = utc_now()
        record.decision_note = (note or "").strip()[:2000] or None
        self.db.flush()
        self.audit.record(
            action="advice.adopt",
            resource_type="advice_record",
            resource_id=str(record.id),
            user_id=actor.id,
            new_value={
                "status": record.status.value,
                "action_item_ids": [item.id for item in created],
                "note": record.decision_note,
            },
        )
        return self.view(record)

    def reject(self, advice_id: int, actor: User, *, note: str) -> dict[str, Any]:
        record = self._decidable(advice_id, actor)
        if len(note.strip()) < 2:
            raise DomainValidationError("请说明不采纳的理由")
        record.status = AdviceStatus.REJECTED
        record.decided_by = actor.id
        record.decided_at = utc_now()
        record.decision_note = note.strip()[:2000]
        self.db.flush()
        self.audit.record(
            action="advice.reject",
            resource_type="advice_record",
            resource_id=str(record.id),
            user_id=actor.id,
            new_value={"status": record.status.value, "note": record.decision_note},
        )
        return self.view(record)

    def link_proposal(self, advice_id: int, proposal_id: str, actor: User) -> dict[str, Any]:
        """Attach the change proposal that this advice led to."""
        record = self._decidable(advice_id, actor)
        if record.status != AdviceStatus.ADOPTED:
            raise DomainValidationError("请先采纳该建议，再关联变更方案")
        record.proposal_id = proposal_id
        self.db.flush()
        self.audit.record(
            action="advice.link_proposal",
            resource_type="advice_record",
            resource_id=str(record.id),
            user_id=actor.id,
            new_value={"proposal_id": proposal_id},
        )
        return self.view(record)

    def evaluate(
        self,
        advice_id: int,
        actor: User,
        *,
        outcome: str,
        issue_resolved: bool,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record what actually happened, separately from whether it was adopted."""
        record = self._decidable(advice_id, actor)
        if record.status != AdviceStatus.ADOPTED:
            raise DomainValidationError("只能评价已采纳的建议")
        open_actions = self.db.scalar(
            select(func.count(ActionItem.id)).where(
                ActionItem.advice_id == record.id,
                ActionItem.status.in_((ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS)),
            )
        )
        record.outcome = AdviceOutcome(outcome)
        record.issue_resolved = issue_resolved
        record.outcome_note = (note or "").strip()[:2000] or None
        record.evaluated_by = actor.id
        record.evaluated_at = utc_now()
        self.db.flush()
        self.audit.record(
            action="advice.evaluate",
            resource_type="advice_record",
            resource_id=str(record.id),
            user_id=actor.id,
            new_value={
                "outcome": record.outcome.value,
                "issue_resolved": issue_resolved,
                "open_action_items_at_evaluation": open_actions,
            },
        )
        result = self.view(record)
        # An evaluation is a claim about the outcome, not proof the work is done.
        result["open_action_items"] = open_actions
        return result

    def effectiveness_summary(self, project_id: int) -> dict[str, Any]:
        rows = list(
            self.db.scalars(select(AdviceRecord).where(AdviceRecord.project_id == project_id))
        )
        evaluated = [row for row in rows if row.outcome is not None]
        return {
            "total": len(rows),
            "adopted": sum(1 for row in rows if row.status == AdviceStatus.ADOPTED),
            "rejected": sum(1 for row in rows if row.status == AdviceStatus.REJECTED),
            "pending": sum(1 for row in rows if row.status == AdviceStatus.PROPOSED),
            "evaluated": len(evaluated),
            "effective": sum(1 for row in evaluated if row.outcome == AdviceOutcome.EFFECTIVE),
            "issues_resolved": sum(1 for row in evaluated if row.issue_resolved),
        }

    # ----------------------------------------------------------------- guard

    def _decidable(self, advice_id: int, actor: User) -> AdviceRecord:
        record = self.db.get(AdviceRecord, advice_id)
        if record is None:
            raise DomainValidationError("建议记录不存在")
        issue = self.db.get(Issue, record.issue_id)
        if issue is None:
            raise IssueNotFoundError
        # Whoever may ask for advice on this issue may also decide on it.
        if not can_request_issue_advice(actor, issue):
            raise PermissionDeniedError(
                "只有管理员、项目负责人、问题登记人或任务负责人可以处置建议"
            )
        if record.status == AdviceStatus.SUPERSEDED:
            raise DomainValidationError("该版本已被新版本取代，请处置最新版本")
        if issue.status == IssueStatus.RESOLVED and record.status == AdviceStatus.PROPOSED:
            raise DomainValidationError("问题已解决，无需再处置该建议")
        return record


__all__ = ["AdviceService", "context_digest"]
