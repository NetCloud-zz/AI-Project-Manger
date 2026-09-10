"""Action item API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import (
    can_create_action_item,
    can_modify_action_item,
    can_view_action_item,
    can_view_project,
)
from app.models.action_item import ActionItemStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.action_item import ActionItemCreate, ActionItemResponse, ActionItemUpdate
from app.services.action_item import ActionItemService
from app.services.exceptions import (
    ActionItemNotFoundError,
    DomainValidationError,
    IssueNotFoundError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.project import ProjectService

router = APIRouter(tags=["action-items"])


def _load_project(db: Session, project_id: int) -> Project:
    try:
        return ProjectService(db).get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc


def _translate_write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=403, detail=exc.message)
    if isinstance(exc, OwnerNotFoundError):
        detail = "Owner not found"
    elif isinstance(exc, TaskNotFoundError):
        detail = "Task not found"
    elif isinstance(exc, IssueNotFoundError):
        detail = "Issue not found"
    else:
        detail = getattr(exc, "message", None) or str(exc)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post(
    "/projects/{project_id}/action-items",
    response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_action_item(
    project_id: int,
    body: ActionItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    project = _load_project(db, project_id)
    if not can_create_action_item(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        item = ActionItemService(db).create_action_item(
            project_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except (
        OwnerNotFoundError,
        TaskNotFoundError,
        IssueNotFoundError,
        DomainValidationError,
        PermissionDeniedError,
    ) as exc:
        raise _translate_write_error(exc) from exc
    db.commit()
    return ActionItemResponse.model_validate(item)


@router.get("/projects/{project_id}/action-items", response_model=list[ActionItemResponse])
def list_project_action_items(
    project_id: int,
    status_filter: ActionItemStatus | None = Query(default=None, alias="status"),
    open_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActionItemResponse]:
    project = _load_project(db, project_id)
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    items = ActionItemService(db).list_action_items(
        current_user,
        project_id=project_id,
        status=status_filter,
        open_only=open_only,
    )
    return [ActionItemResponse.model_validate(item) for item in items]


@router.get("/action-items", response_model=list[ActionItemResponse])
def list_action_items(
    project_id: int | None = Query(default=None),
    task_id: int | None = Query(default=None),
    issue_id: int | None = Query(default=None),
    owner_id: int | None = Query(default=None),
    status_filter: ActionItemStatus | None = Query(default=None, alias="status"),
    open_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActionItemResponse]:
    items = ActionItemService(db).list_action_items(
        current_user,
        project_id=project_id,
        task_id=task_id,
        issue_id=issue_id,
        owner_id=owner_id,
        status=status_filter,
        open_only=open_only,
    )
    return [ActionItemResponse.model_validate(item) for item in items]


@router.get("/action-items/{action_item_id}", response_model=ActionItemResponse)
def get_action_item(
    action_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    try:
        item = ActionItemService(db).get_action_item(action_item_id)
    except ActionItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        ) from exc
    if not can_view_action_item(db, current_user, item):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return ActionItemResponse.model_validate(item)


@router.patch("/action-items/{action_item_id}", response_model=ActionItemResponse)
def update_action_item(
    action_item_id: int,
    body: ActionItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActionItemResponse:
    service = ActionItemService(db)
    try:
        item = service.get_action_item(action_item_id)
    except ActionItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action item not found"
        ) from exc
    if not can_modify_action_item(current_user, item, item.project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        updated = service.update_action_item(
            action_item_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except (
        OwnerNotFoundError,
        TaskNotFoundError,
        IssueNotFoundError,
        DomainValidationError,
        PermissionDeniedError,
    ) as exc:
        raise _translate_write_error(exc) from exc
    db.commit()
    return ActionItemResponse.model_validate(updated)
