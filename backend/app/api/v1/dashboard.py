"""Dashboard API routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.permissions import can_view_dashboard, can_view_personal_dashboard
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.dashboard import DashboardResponse, PersonalDashboardResponse
from app.services.business_clock import BusinessClock
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse | PersonalDashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse | PersonalDashboardResponse:
    if can_view_dashboard(current_user):
        return DashboardService(db).get_dashboard(current_user)
    if can_view_personal_dashboard(current_user):
        return _personal_dashboard(db, current_user)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
    )


def _personal_dashboard(db: Session, user: User) -> PersonalDashboardResponse:
    today = BusinessClock().today()
    stmt = select(Task).where(
        Task.owner_id == user.id,
        Task.status.in_((TaskStatus.TODO, TaskStatus.IN_PROGRESS)),
    )
    tasks = list(db.scalars(stmt).all())
    overdue = sum(1 for task in tasks if task.due_date is not None and task.due_date < today)
    return PersonalDashboardResponse(
        my_active_tasks=len(tasks),
        my_overdue_tasks=overdue,
    )
