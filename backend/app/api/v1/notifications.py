"""S4 notification records. Delivery state and business acknowledgement are separate."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.notification_delivery import NotificationDeliveryService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def service(db: Session = Depends(get_db)) -> Iterator[NotificationDeliveryService]:
    try:
        yield NotificationDeliveryService(db)
    except PermissionDeniedError as exc:
        db.rollback()
        raise HTTPException(403, detail=exc.message) from exc
    except DomainValidationError as exc:
        db.rollback()
        raise HTTPException(400, detail=exc.message) from exc


@router.get("", summary="Notifications addressed to the current user")
def list_my_notifications(
    status: str | None = Query(default=None, pattern="^(QUEUED|SENT|FAILED|ACKNOWLEDGED)$"),
    limit: int = Query(default=50, ge=1, le=200),
    svc: NotificationDeliveryService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    return svc.list_for_user(actor, status=status, limit=limit)


@router.post("/{event_id}/acknowledge", summary="Recipient confirms they have seen the change")
def acknowledge(
    event_id: int,
    svc: NotificationDeliveryService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    result = svc.acknowledge(event_id, actor)
    svc.db.commit()
    return result


@router.post("/{event_id}/retry", summary="Manually resend a failed notification")
def retry(
    event_id: int,
    svc: NotificationDeliveryService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    result = svc.requeue(event_id, actor)
    svc.db.commit()
    from app.workers.tasks import enqueue_plan_notifications

    enqueue_plan_notifications()
    return result
