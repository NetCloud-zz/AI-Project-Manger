"""Issue API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import (
    can_create_issue,
    can_modify_issue,
    can_request_issue_advice,
    can_view_issue,
    can_view_project,
)
from app.models.issue import IssueStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.issue import IssueAdviseResponse, IssueCreate, IssueResponse, IssueUpdate
from app.services.exceptions import (
    DomainValidationError,
    IssueNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.issue import IssueService
from app.services.project import ProjectService
from app.workers.tasks import enqueue_advise_issue

router = APIRouter(tags=["issues"])


def _load_project(db: Session, project_id: int) -> Project:
    try:
        return ProjectService(db).get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_issue(
    project_id: int,
    body: IssueCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IssueResponse:
    """Manually log a problem. Omit task_id for a project-level issue."""
    project = _load_project(db, project_id)
    if not can_create_issue(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        issue = IssueService(db).create_issue(
            project_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Task not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return IssueResponse.model_validate(issue)


@router.get("/projects/{project_id}/issues", response_model=list[IssueResponse])
def list_project_issues(
    project_id: int,
    status_filter: IssueStatus | None = Query(default=None, alias="status"),
    open_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IssueResponse]:
    project = _load_project(db, project_id)
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    issues = IssueService(db).list_issues(
        current_user,
        project_id=project_id,
        status=status_filter,
        open_only=open_only,
    )
    return [IssueResponse.model_validate(item) for item in issues]


@router.get("/issues", response_model=list[IssueResponse])
def list_issues(
    project_id: int | None = Query(default=None),
    task_id: int | None = Query(default=None),
    status_filter: IssueStatus | None = Query(default=None, alias="status"),
    open_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[IssueResponse]:
    issues = IssueService(db).list_issues(
        current_user,
        project_id=project_id,
        task_id=task_id,
        status=status_filter,
        open_only=open_only,
    )
    return [IssueResponse.model_validate(item) for item in issues]


@router.get("/issues/{issue_id}", response_model=IssueResponse)
def get_issue(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IssueResponse:
    service = IssueService(db)
    try:
        issue = service.get_issue(issue_id)
    except IssueNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        ) from exc
    if not can_view_issue(db, current_user, issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return IssueResponse.model_validate(issue)


@router.patch("/issues/{issue_id}", response_model=IssueResponse)
def update_issue(
    issue_id: int,
    body: IssueUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IssueResponse:
    service = IssueService(db)
    try:
        issue = service.get_issue(issue_id)
    except IssueNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        ) from exc
    if not can_modify_issue(current_user, issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    updated = service.update_issue(
        issue_id,
        body,
        actor=current_user,
        ip_address=get_client_ip(request),
    )
    db.commit()
    return IssueResponse.model_validate(updated)


@router.post(
    "/issues/{issue_id}/advise",
    response_model=IssueAdviseResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_issue_advice(
    issue_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IssueAdviseResponse:
    """Request AI suggested solution (async via worker)."""
    service = IssueService(db)
    try:
        issue = service.get_issue(issue_id)
    except IssueNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        ) from exc
    if not can_view_issue(db, current_user, issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    if not can_request_issue_advice(current_user, issue):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    from app.models.ai_run import AIRunType
    from app.services.ai_run import AIRunService

    run = AIRunService(db).create_queued(
        run_type=AIRunType.ISSUE_ADVICE,
        resource_type="issue",
        resource_id=issue_id,
        created_by=current_user.id,
    )
    db.commit()
    enqueue_advise_issue(
        issue_id,
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        run_id=run.id,
    )
    return IssueAdviseResponse(
        status="queued",
        message="AI advice generation queued",
        ai_run_id=run.id,
    )
