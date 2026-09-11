"""Risk event and advice record routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.permissions import can_view_full_project, can_view_project
from app.models.project import Project
from app.models.user import User
from app.schemas.risk_advice import (
    AdviceAdoptRequest,
    AdviceEvaluateRequest,
    AdviceLinkProposalRequest,
    AdviceRejectRequest,
    RiskRefreshRequest,
    RiskResolveRequest,
)
from app.services.advice import AdviceService
from app.services.exceptions import (
    DomainValidationError,
    IssueNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.services.project_context import ProjectContextService
from app.services.risk_event import RiskEventService, open_risk_summary

router = APIRouter(tags=["risks"])


def _project(db: Session, project_id: int, actor: User) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not can_view_project(db, actor, project):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return project


def _guard(call):  # type: ignore[no-untyped-def]
    try:
        return call()
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except (IssueNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


# ------------------------------------------------------------------- risks


@router.get("/projects/{project_id}/risk-events")
def list_risk_events(
    project_id: int,
    status_filter: str | None = Query(default="OPEN", alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Tracked risks for one project. Without full access only own-task risks."""
    _project(db, project_id, current_user)
    if status_filter not in (None, "", "OPEN", "RESOLVED"):
        raise HTTPException(status_code=400, detail="status 只能是 OPEN 或 RESOLVED")
    service = RiskEventService(db)
    items = _guard(
        lambda: service.list_for_project(project_id, current_user, status=status_filter or None)
    )
    return {"items": items, "summary": open_risk_summary(db, project_id)}


@router.post("/projects/{project_id}/risk-events/refresh")
def refresh_risk_events(
    project_id: int,
    body: RiskRefreshRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-run the detectors now instead of waiting for the daily scan."""
    project = _project(db, project_id, current_user)
    if not can_view_full_project(db, current_user, project):
        raise HTTPException(status_code=403, detail="只有项目负责人、管理员或管理层可以触发重评")
    service = RiskEventService(db)
    counts = service.detect(project, with_forecast=(body.with_forecast if body else True))
    db.commit()
    return {
        "counts": counts,
        "items": service.list_for_project(project_id, current_user, status="OPEN"),
        "summary": open_risk_summary(db, project_id),
    }


@router.post("/risk-events/{event_id}/resolve")
def resolve_risk_event(
    event_id: int,
    body: RiskResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Close a risk with a stated reason.

    If the detector still finds the condition, the next run reopens it. That is
    intentional: a manual close is a judgement, not a fix.
    """
    service = RiskEventService(db)
    result = _guard(lambda: service.resolve(event_id, current_user, body.resolution))
    db.commit()
    return result


# ------------------------------------------------------------------ context


@router.get("/issues/{issue_id}/context")
def get_issue_context(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The evidence set an advice request would be built from, before asking anything."""
    from app.core.permissions import can_view_issue
    from app.models.issue import Issue

    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    if not can_view_issue(db, current_user, issue):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return ProjectContextService(db).for_issue(issue).as_dict()


# ------------------------------------------------------------------- advice


@router.get("/issues/{issue_id}/advice")
def list_issue_advice(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = AdviceService(db)
    return {"items": _guard(lambda: service.list_for_issue(issue_id, current_user))}


@router.get("/projects/{project_id}/advice")
def list_project_advice(
    project_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _project(db, project_id, current_user)
    service = AdviceService(db)
    return {
        "items": _guard(
            lambda: service.list_for_project(project_id, current_user, status=status_filter)
        ),
        "effectiveness": service.effectiveness_summary(project_id),
    }


@router.get("/advice/{advice_id}")
def get_advice(
    advice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = AdviceService(db)
    record = _guard(lambda: service.get(advice_id, current_user))
    return service.view(record)


@router.post("/advice/{advice_id}/adopt", status_code=status.HTTP_200_OK)
def adopt_advice(
    advice_id: int,
    body: AdviceAdoptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Accept advice and create the follow-up actions.

    This does not move any dates. Plan changes still go through a change
    proposal, which is where authorization and atomic execution live.
    """
    service = AdviceService(db)
    result = _guard(
        lambda: service.adopt(
            advice_id,
            current_user,
            note=body.note,
            actions=[item.model_dump(mode="json") for item in body.actions],
        )
    )
    db.commit()
    return result


@router.post("/advice/{advice_id}/reject")
def reject_advice(
    advice_id: int,
    body: AdviceRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = AdviceService(db)
    result = _guard(lambda: service.reject(advice_id, current_user, note=body.note))
    db.commit()
    return result


@router.post("/advice/{advice_id}/proposal")
def link_advice_proposal(
    advice_id: int,
    body: AdviceLinkProposalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service = AdviceService(db)
    result = _guard(lambda: service.link_proposal(advice_id, body.proposal_id, current_user))
    db.commit()
    return result


@router.post("/advice/{advice_id}/evaluate")
def evaluate_advice(
    advice_id: int,
    body: AdviceEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Record whether the adopted advice actually helped."""
    service = AdviceService(db)
    result = _guard(
        lambda: service.evaluate(
            advice_id,
            current_user,
            outcome=body.outcome,
            issue_resolved=body.issue_resolved,
            note=body.note,
        )
    )
    db.commit()
    return result
