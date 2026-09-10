"""Progress update API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import can_submit_progress, can_view_project, can_view_task
from app.models.user import User
from app.schemas.progress import ProgressSubmit, ProgressUpdateResponse, RecentProgressItem
from app.services.exceptions import ProjectNotFoundError, TaskNotFoundError
from app.services.progress import ProgressService
from app.services.project import ProjectService
from app.services.task import TaskService

router = APIRouter(tags=["progress"])


@router.post(
    "/tasks/{task_id}/progress",
    response_model=ProgressUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_progress(
    task_id: int,
    body: ProgressSubmit,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProgressUpdateResponse:
    task_service = TaskService(db)
    try:
        task = task_service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_submit_progress(current_user, task, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    progress = ProgressService(db).submit_progress(
        task_id,
        body,
        actor=current_user,
        ip_address=get_client_ip(request),
    )
    from app.models.ai_run import AIRunType
    from app.services.ai_run import AIRunService

    run = AIRunService(db).create_queued(
        run_type=AIRunType.PROGRESS_ANALYSIS,
        resource_type="progress_update",
        resource_id=progress.id,
        created_by=current_user.id,
    )
    db.commit()

    try:
        from app.workers.tasks import enqueue_analyze_progress

        enqueue_analyze_progress(progress.id, run_id=run.id)
    except Exception:
        pass

    return ProgressUpdateResponse.model_validate(progress)


@router.post(
    "/tasks/{task_id}/progress/{progress_id}/reanalyze",
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_progress(
    task_id: int,
    progress_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Re-queue AI analysis for an existing progress update."""
    task_service = TaskService(db)
    try:
        task = task_service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None or not can_submit_progress(current_user, task, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    progress = ProgressService(db).get_progress(progress_id)
    if progress is None or progress.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Progress not found")

    # Clear previous AI fields so worker will re-run.
    progress.summary = None
    progress.ai_status = None
    progress.risk_detected = None
    progress.ai_analysis_failed = False
    db.add(progress)

    from app.models.ai_run import AIRunType
    from app.services.ai_run import AIRunService

    run = AIRunService(db).create_queued(
        run_type=AIRunType.PROGRESS_ANALYSIS,
        resource_type="progress_update",
        resource_id=progress.id,
        created_by=current_user.id,
    )
    db.commit()
    from app.workers.tasks import enqueue_analyze_progress

    enqueue_analyze_progress(progress.id, run_id=run.id)
    return {"status": "queued", "ai_run_id": run.id}


@router.get("/tasks/{task_id}/progress", response_model=list[ProgressUpdateResponse])
def list_task_progress(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProgressUpdateResponse]:
    task_service = TaskService(db)
    try:
        task = task_service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    if not can_view_task(db, current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    items = ProgressService(db).list_task_progress(task_id)
    return [ProgressUpdateResponse.model_validate(item) for item in items]


@router.get("/projects/{project_id}/progress/recent", response_model=list[RecentProgressItem])
def list_project_recent_progress(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RecentProgressItem]:
    project_service = ProjectService(db)
    try:
        project = project_service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    items = ProgressService(db).list_recent_by_project(project_id, limit=limit)
    return [
        RecentProgressItem(
            id=item.id,
            task_id=item.task_id,
            task_name=item.task.task_name if item.task else "",
            user_id=item.user_id,
            user_name=item.user.name if item.user else str(item.user_id),
            raw_content=item.raw_content,
            summary=item.summary,
            created_at=item.created_at,
        )
        for item in items
        if item.task and can_view_task(db, current_user, item.task)
    ]
