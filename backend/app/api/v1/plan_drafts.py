"""S4 conversational project drafting. Publication is a separate, explicit act."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.plan_draft import (
    PlanDraftCreate,
    PlanDraftPublish,
    PlanDraftRevision,
    PlanDraftUpdate,
)
from app.services.change_proposal import ProposalConflict
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.plan_draft import PlanDraftService

router = APIRouter(prefix="/plan-drafts", tags=["plan-drafts"])


def service(db: Session = Depends(get_db)) -> Iterator[PlanDraftService]:
    try:
        yield PlanDraftService(db)
    except PermissionDeniedError as exc:
        db.rollback()
        raise HTTPException(403, detail=exc.message) from exc
    except ProposalConflict as exc:
        db.rollback()
        raise HTTPException(409, detail=exc.message) from exc
    except DomainValidationError as exc:
        db.rollback()
        raise HTTPException(400, detail=exc.message) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="并发或重复请求，请重新读取草案") from exc


def finish[T](svc: PlanDraftService, value: T) -> T:
    svc.db.commit()
    return value


@router.get("", summary="List my plan drafts")
def list_drafts(
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    return svc.list_drafts(actor)


@router.post("", summary="Create a project plan draft")
def create_draft(
    body: PlanDraftCreate,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.create(body, actor))


@router.get("/{draft_id}")
def get_draft(
    draft_id: str,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return svc.get(draft_id, actor)


@router.put("/{draft_id}")
def update_draft(
    draft_id: str,
    body: PlanDraftUpdate,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.update(draft_id, body, actor))


@router.post("/{draft_id}/review", summary="Check completeness and consistency")
def review_draft(
    draft_id: str,
    body: PlanDraftRevision,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.review(draft_id, body, actor))


@router.post("/{draft_id}/publish", summary="Create the project and its plan in one transaction")
def publish_draft(
    draft_id: str,
    body: PlanDraftPublish,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.publish(draft_id, body, actor))


@router.post("/{draft_id}/discard")
def discard_draft(
    draft_id: str,
    body: PlanDraftRevision,
    svc: PlanDraftService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.discard(draft_id, body, actor))
