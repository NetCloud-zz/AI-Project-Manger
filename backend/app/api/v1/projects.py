"""Project API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import (
    can_create_project,
    can_modify_project,
    can_modify_project_schedule,
    can_view_full_project,
    can_view_project,
)
from app.models.user import User
from app.schemas.daily_summary import DailySummaryResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectDeleteRequest,
    ProjectOwnerBrief,
    ProjectOwnersUpdate,
    ProjectResponse,
    ProjectScheduleUpdate,
    ProjectUpdate,
)
from app.services.daily_summary import DailySummaryService
from app.services.exceptions import (
    DomainValidationError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectCodeExistsError,
    ProjectNotFoundError,
)
from app.services.project import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    if not can_create_project(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    service = ProjectService(db)
    try:
        project = service.create_project(
            body, actor=current_user, ip_address=get_client_ip(request)
        )
    except ProjectCodeExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Project code exists"
        ) from exc
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    projects = ProjectService(db).list_projects(current_user)
    return [ProjectResponse.model_validate(item) for item in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        updated = service.update_project(
            project_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return ProjectResponse.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    body: ProjectDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Hard-delete a project. Only project owners or admins; reason is audited."""
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只有项目负责人或管理员可以删除项目"
        )
    try:
        service.delete_project(
            project_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()


@router.put("/{project_id}/owners", response_model=ProjectResponse)
def replace_project_owners(
    project_id: int,
    body: ProjectOwnersUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        updated = service.update_owners(
            project_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    db.commit()
    return ProjectResponse.model_validate(updated)


@router.patch("/{project_id}/schedule", response_model=ProjectResponse)
def update_project_schedule(
    project_id: int,
    body: ProjectScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    """Change overall project dates. Requires a written change_reason."""
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project_schedule(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        updated = service.update_schedule(
            project_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return ProjectResponse.model_validate(updated)


@router.get("/{project_id}/assignable-users", response_model=list[ProjectOwnerBrief])
def list_assignable_users(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectOwnerBrief]:
    """Users that can be set as project owners or task owners on this project."""
    from app.models.user import UserRole, UserStatus
    from app.repositories.user import UserRepository

    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    users = UserRepository(db).list_all()
    active = [u for u in users if u.status == UserStatus.ACTIVE]
    if current_user.role != UserRole.ADMIN:
        # Non-admins see project owners / members / POs / admins only.
        from sqlalchemy import select

        from app.models.task import Task

        participant_ids = set(
            db.scalars(select(Task.owner_id).where(Task.project_id == project_id)).all()
        )
        participant_ids.add(project.owner_id)
        participant_ids.update(o.id for o in project.owners)
        active = [
            u
            for u in active
            if u.id in participant_ids
            or u.role in (UserRole.ADMIN, UserRole.PROJECT_OWNER, UserRole.EXECUTIVE)
        ]
    return [ProjectOwnerBrief.model_validate(u) for u in active]


@router.get("/{project_id}/summaries", response_model=list[DailySummaryResponse])
def list_project_summaries(
    project_id: int,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DailySummaryResponse]:
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    if not can_view_full_project(db, current_user, project):
        return []
    summaries = DailySummaryService(db).list_summaries(project_id, limit=limit)
    return [DailySummaryResponse.model_validate(item) for item in summaries]


@router.get("/{project_id}/summaries/latest", response_model=DailySummaryResponse | None)
def get_latest_project_summary(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DailySummaryResponse | None:
    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    if not can_view_full_project(db, current_user, project):
        return None
    summary = DailySummaryService(db).get_latest_summary(project_id)
    if summary is None:
        return None
    return DailySummaryResponse.model_validate(summary)


@router.post(
    "/{project_id}/summaries/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_project_summary(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Queue/regenerate today's daily summary for a project (ADMIN / owner)."""
    from app.core.permissions import can_modify_project
    from app.models.ai_run import AIRunType
    from app.services.ai_run import AIRunService
    from app.workers.tasks import enqueue_generate_project_summary

    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    run = AIRunService(db).create_queued(
        run_type=AIRunType.DAILY_SUMMARY,
        resource_type="project",
        resource_id=project_id,
        created_by=current_user.id,
    )
    db.commit()
    enqueue_generate_project_summary(project_id, run_id=run.id)
    return {"status": "queued", "ai_run_id": run.id}


@router.get("/{project_id}/forecast")
def get_project_forecast(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Predicted finish date and critical path for the plan as it stands today."""
    from app.services.scheduling import SchedulingService

    try:
        return SchedulingService(db).forecast(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        ) from exc
    except DomainValidationError as exc:
        # A calendar or graph the engine cannot read is a data problem, not a
        # server fault; say so instead of returning a fabricated date.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message
        ) from exc


@router.get("/{project_id}/data-integrity")
def get_project_data_integrity(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """List data gaps that make this project's schedule or forecast unreliable."""
    from app.services.data_integrity import DataIntegrityService, summarise

    service = ProjectService(db)
    try:
        project = service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return summarise(DataIntegrityService(db).check_project(project))
