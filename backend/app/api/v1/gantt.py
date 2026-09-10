"""Gantt data and task dependency routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import can_modify_project, can_view_project, can_view_task
from app.models.project import Project
from app.models.user import User
from app.schemas.task import (
    ProjectGanttResponse,
    TaskLinkCreate,
    TaskLinkResponse,
    TaskLinkUpdate,
    TaskResponse,
)
from app.services.exceptions import (
    DomainValidationError,
    ProjectNotFoundError,
    TaskLinkNotFoundError,
    TaskNotFoundError,
)
from app.services.project import ProjectService
from app.services.task import TaskService
from app.services.task_link import TaskLinkService

router = APIRouter(tags=["gantt"])


def _load_viewable_project(db: Session, project_id: int, current_user: User) -> Project:
    try:
        project = ProjectService(db).get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_view_project(db, current_user, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return project


def _require_project_editor(db: Session, project_id: int, current_user: User) -> Project:
    project = _load_viewable_project(db, project_id, current_user)
    if not can_modify_project(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return project


@router.get("/projects/{project_id}/gantt", response_model=ProjectGanttResponse)
def get_project_gantt(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectGanttResponse:
    project = _load_viewable_project(db, project_id, current_user)

    tasks = TaskService(db).list_project_tasks(project_id)
    tasks = [task for task in tasks if can_view_task(db, current_user, task)]

    visible_ids = {task.id for task in tasks}
    links = [
        link
        for link in TaskLinkService(db).list_project_links(project_id)
        if link.source_id in visible_ids and link.target_id in visible_ids
    ]

    return ProjectGanttResponse(
        project_id=project.id,
        project_code=project.project_code,
        project_name=project.project_name,
        target_date=project.target_date,
        editable=can_modify_project(current_user, project, db),
        tasks=[TaskResponse.model_validate(item) for item in tasks],
        links=[TaskLinkResponse.model_validate(item) for item in links],
    )


@router.post(
    "/projects/{project_id}/task-links",
    response_model=TaskLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_link(
    project_id: int,
    body: TaskLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskLinkResponse:
    _require_project_editor(db, project_id, current_user)
    try:
        link = TaskLinkService(db).create_link(
            project_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return TaskLinkResponse.model_validate(link)


@router.patch("/task-links/{link_id}", response_model=TaskLinkResponse)
def update_task_link(
    link_id: int,
    body: TaskLinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskLinkResponse:
    service = TaskLinkService(db)
    try:
        existing = service.get_link(link_id)
    except TaskLinkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task link not found"
        ) from exc
    _require_project_editor(db, existing.project_id, current_user)
    link = service.update_link(link_id, body, actor=current_user, ip_address=get_client_ip(request))
    db.commit()
    return TaskLinkResponse.model_validate(link)


@router.delete("/task-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    service = TaskLinkService(db)
    try:
        existing = service.get_link(link_id)
    except TaskLinkNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task link not found"
        ) from exc
    _require_project_editor(db, existing.project_id, current_user)
    service.delete_link(link_id, actor=current_user, ip_address=get_client_ip(request))
    db.commit()
