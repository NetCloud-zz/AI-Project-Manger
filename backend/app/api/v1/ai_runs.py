"""AIRun status APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.permissions import (
    can_view_issue,
    can_view_project,
    can_view_task,
)
from app.models.ai_run import AIRun, AIRunType
from app.models.issue import Issue
from app.models.project import Project
from app.models.task import Task
from app.models.user import User, UserRole
from app.schemas.ai_run import AIRunResponse
from app.services.ai_run import AIRunService

router = APIRouter(prefix="/ai-runs", tags=["ai-runs"])


def _parse_int_id(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def assert_can_view_ai_resource(
    db: Session,
    user: User,
    *,
    resource_type: str,
    resource_id: str,
) -> None:
    """Object-level gate for AI run reads. Unknown types are denied."""
    if user.role == UserRole.ADMIN:
        return

    kind = resource_type.strip().lower()
    rid = _parse_int_id(resource_id)
    if rid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if kind in {"project", "daily_project_summary", "plan_draft", "change_proposal"}:
        project = db.get(Project, rid)
        if project is None or not can_view_project(db, user, project):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind == "task":
        task = db.get(Task, rid)
        if task is None or not can_view_task(db, user, task):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind in {"issue"}:
        issue = db.get(Issue, rid)
        if issue is None or not can_view_issue(db, user, issue):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind == "advice_record":
        from app.models.advice_record import AdviceRecord

        advice = db.get(AdviceRecord, rid)
        if advice is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        issue = db.get(Issue, advice.issue_id)
        if issue is None or not can_view_issue(db, user, issue):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind == "progress_update":
        from app.models.progress_update import ProgressUpdate

        progress = db.get(ProgressUpdate, rid)
        if progress is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        task = db.get(Task, progress.task_id)
        if task is None or not can_view_task(db, user, task):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind == "risk_event":
        from app.models.risk_event import RiskEvent

        event = db.get(RiskEvent, rid)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        project = db.get(Project, event.project_id)
        if project is None or not can_view_project(db, user, project):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    if kind == "notification_event":
        from app.models.notification import NotificationEvent

        event = db.get(NotificationEvent, rid)
        if event is None or event.recipient_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return

    # Fail closed for unfamiliar resource types (do not leak existence).
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")


def assert_can_view_ai_run(db: Session, user: User, run: AIRun) -> None:
    assert_can_view_ai_resource(
        db,
        user,
        resource_type=run.resource_type,
        resource_id=run.resource_id,
    )


@router.get("/latest/by-resource", response_model=AIRunResponse | None)
def latest_ai_run(
    resource_type: str = Query(..., min_length=1, max_length=64),
    resource_id: str = Query(..., min_length=1, max_length=64),
    run_type: AIRunType | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIRunResponse | None:
    assert_can_view_ai_resource(
        db,
        current_user,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    run = AIRunService(db).latest(
        resource_type=resource_type,
        resource_id=resource_id,
        run_type=run_type,
    )
    if run is None:
        return None
    return AIRunResponse.model_validate(run)


@router.get("/{run_id}", response_model=AIRunResponse)
def get_ai_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIRunResponse:
    run = AIRunService(db).get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found")
    assert_can_view_ai_run(db, current_user, run)
    return AIRunResponse.model_validate(run)
