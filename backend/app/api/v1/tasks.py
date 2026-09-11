"""Task API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_client_ip, get_current_user
from app.core.permissions import (
    can_create_task,
    can_modify_task_core,
    can_modify_task_status,
    can_view_project,
    can_view_task,
)
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.task import (
    MyTasksPage,
    TaskBranchActivate,
    TaskBranchCreate,
    TaskCreate,
    TaskDeleteRequest,
    TaskResponse,
    TaskUpdate,
)
from app.services.exceptions import (
    DomainValidationError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
    VersionConflictError,
)
from app.services.project import ProjectService
from app.services.task import TaskService

router = APIRouter(tags=["tasks"])


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    project_id: int,
    body: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    project_service = ProjectService(db)
    try:
        project = project_service.get_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        ) from exc
    if not can_create_task(current_user, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    service = TaskService(db)
    try:
        task = service.create_task(
            project_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    return TaskResponse.model_validate(task)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
def list_project_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskResponse]:
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
    tasks = TaskService(db).list_project_tasks(project_id)
    tasks = [task for task in tasks if can_view_task(db, current_user, task)]
    return [TaskResponse.model_validate(item) for item in tasks]


@router.get("/tasks/my", response_model=MyTasksPage)
def list_my_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: TaskStatus | None = Query(None, alias="status"),
    q: str | None = Query(None, max_length=200),
    sort: str = Query("due", pattern="^(due|name|project)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MyTasksPage:
    tasks, total = TaskService(db).list_my_tasks_page(
        current_user,
        page=page,
        page_size=page_size,
        status=status_filter,
        q=q,
        sort=sort,
    )
    return MyTasksPage(
        items=[TaskResponse.model_validate(item) for item in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    if not can_view_task(db, current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    body: TaskUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_modify_task_status(current_user, task, project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )

    allow_core = can_modify_task_core(current_user, task, project, db)
    try:
        updated = service.update_task(
            task_id,
            body,
            actor=current_user,
            allow_core_fields=allow_core,
            ip_address=get_client_ip(request),
        )
    except VersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "Task was modified by another request; refresh and retry",
                "current": exc.current,
            },
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    db.commit()
    return TaskResponse.model_validate(updated)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    body: TaskDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Hard-delete a task. Only project owners or admins; reason is audited."""
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_modify_task_core(current_user, task, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="只有项目负责人或管理员可以删除任务"
        )
    try:
        service.delete_task(
            task_id,
            body,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()


@router.get("/tasks/{task_id}/branches", response_model=list[TaskResponse])
def list_task_branches(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    if not can_view_task(db, current_user, task):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return [
        TaskResponse.model_validate(item)
        for item in service.list_branch_siblings(task_id)
        if can_view_task(db, current_user, item)
    ]


@router.post(
    "/tasks/{task_id}/branches",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_branch(
    task_id: int,
    body: TaskBranchCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_modify_task_core(current_user, task, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        branch = service.create_branch(
            task_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except OwnerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner not found"
        ) from exc
    db.commit()
    return TaskResponse.model_validate(branch)


@router.post("/tasks/{task_id}/activate-branch", response_model=TaskResponse)
def activate_task_branch(
    task_id: int,
    body: TaskBranchActivate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    service = TaskService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from exc
    project = task.project
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_modify_task_core(current_user, task, project, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    try:
        updated = service.activate_branch(
            task_id, body, actor=current_user, ip_address=get_client_ip(request)
        )
    except DomainValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    db.commit()
    return TaskResponse.model_validate(updated)
