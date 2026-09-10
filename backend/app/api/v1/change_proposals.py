"""S3 review endpoints. Authentication, not request JSON, supplies the confirmer."""

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.change_proposal import (
    ProposalApply,
    ProposalConfirmation,
    ProposalCreate,
    ProposalEdit,
    ProposalRevision,
)
from app.services.change_proposal import ChangeProposalService, ProposalConflict
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.services.planning import record

router = APIRouter(
    prefix="/projects/{project_id}/planning/change-proposals", tags=["change-proposals"]
)


def service(db: Session = Depends(get_db)) -> Iterator[ChangeProposalService]:
    try:
        yield ChangeProposalService(db)
    except PermissionDeniedError as exc:
        db.rollback()
        raise HTTPException(403, detail=exc.message) from exc
    except ProjectNotFoundError as exc:
        db.rollback()
        raise HTTPException(404, detail="Project not found") from exc
    except ProposalConflict as exc:
        db.rollback()
        raise HTTPException(409, detail=exc.message) from exc
    except DomainValidationError as exc:
        db.rollback()
        raise HTTPException(400, detail=exc.message) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="并发或重复请求，请重新读取方案") from exc


def finish[T](svc: ChangeProposalService, value: T) -> T:
    svc.db.commit()
    return value


@router.get("")
def list_proposals(
    project_id: int,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    return svc.list_proposals(project_id, actor)


@router.post("")
def create_proposal(
    project_id: int,
    body: ProposalCreate,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.create(project_id, body, actor))


@router.get("/{proposal_id}")
def get_proposal(
    project_id: int,
    proposal_id: str,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return record(svc.get(project_id, proposal_id, actor))


@router.put("/{proposal_id}")
def edit_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalEdit,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.edit(project_id, proposal_id, body, actor))


@router.post("/{proposal_id}/validate")
def validate_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalRevision,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.validate(project_id, proposal_id, body, actor))


@router.post("/{proposal_id}/confirm")
def confirm_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalConfirmation,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.confirm(project_id, proposal_id, body, actor))


@router.post("/{proposal_id}/apply")
def apply_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalApply,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    result = finish(svc, svc.apply(project_id, proposal_id, body, actor))
    if result.get("status") == "APPLIED":
        # Events are already committed; the worker owns actual delivery.
        from app.workers.tasks import enqueue_plan_notifications

        enqueue_plan_notifications()
    return result


@router.get("/{proposal_id}/notifications", summary="Delivery state of this proposal's notices")
def proposal_notifications(
    project_id: int,
    proposal_id: str,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    from app.services.notification_delivery import NotificationDeliveryService

    return NotificationDeliveryService(svc.db).list_for_proposal(project_id, proposal_id, actor)


@router.post("/{proposal_id}/reject")
def reject_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalRevision,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.reject(project_id, proposal_id, body, actor))


@router.post("/{proposal_id}/compensate")
def compensate_proposal(
    project_id: int,
    proposal_id: str,
    body: ProposalApply,
    svc: ChangeProposalService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.compensate(project_id, proposal_id, body, actor))
