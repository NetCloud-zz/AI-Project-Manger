"""Project planning API. Domain service enforces permissions for every entry point."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.planning import (
    BranchGroupInput,
    BranchGroupUpdateInput,
    BranchOptionInput,
    BranchSelectInput,
    CalendarInput,
    MemberInput,
    MilestoneInput,
    ParticipantsInput,
    PlanVersionInput,
    TaskGroupInput,
)
from app.schemas.scheduling import SchedulePreviewInput
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
)
from app.services.planning import PlanningService

router = APIRouter(prefix="/projects/{project_id}/planning", tags=["planning"])


def service(db: Session = Depends(get_db)) -> Iterator[PlanningService]:
    try:
        yield PlanningService(db)
    except PermissionDeniedError as exc:
        db.rollback()
        raise HTTPException(403, detail=exc.message) from exc
    except ProjectNotFoundError as exc:
        db.rollback()
        raise HTTPException(404, detail="Project not found") from exc
    except DomainValidationError as exc:
        db.rollback()
        raise HTTPException(400, detail=exc.message) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="Concurrent or duplicate change; reload and retry") from exc


def finish[Result](svc: PlanningService, result: Result) -> Result:
    svc.db.commit()
    return result


@router.get("")
def context(
    project_id: int,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.context(project_id, actor))


@router.put("/members/{user_id}")
def member(
    project_id: int,
    user_id: int,
    body: MemberInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_member(project_id, user_id, body, actor))


@router.get("/tasks/{task_id}/participants")
def participants(
    project_id: int,
    task_id: int,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    from app.models.task import Task

    svc.project(project_id, actor)
    svc.scoped(Task, task_id, project_id)
    return finish(svc, svc.participants(task_id, actor))


@router.put("/tasks/{task_id}/participants")
def put_participants(
    project_id: int,
    task_id: int,
    body: ParticipantsInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> list[dict]:
    return finish(svc, svc.put_participants(project_id, task_id, body, actor))


@router.put("/calendar")
def calendar(
    project_id: int,
    body: CalendarInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_calendar(project_id, body, actor))


@router.post("/milestones")
def create_milestone(
    project_id: int,
    body: MilestoneInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_milestone(project_id, body, actor))


@router.put("/milestones/{row_id}")
def milestone(
    project_id: int,
    row_id: int,
    body: MilestoneInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_milestone(project_id, body, actor, row_id))


@router.post("/task-groups")
def create_task_group(
    project_id: int,
    body: TaskGroupInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_task_group(project_id, body, actor))


@router.put("/task-groups/{row_id}")
def task_group(
    project_id: int,
    row_id: int,
    body: TaskGroupInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.put_task_group(project_id, body, actor, row_id))


@router.post("/branch-groups")
def branch_group(
    project_id: int,
    body: BranchGroupInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.create_branch_group(project_id, body, actor))


@router.post("/branch-groups/{group_id}/options")
def branch_option(
    project_id: int,
    group_id: int,
    body: BranchOptionInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.create_branch_option(project_id, group_id, body, actor))


@router.post("/branch-groups/{group_id}/select")
def select_branch(
    project_id: int,
    group_id: int,
    body: BranchSelectInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    svc.project(project_id, actor, write=True, full=True)
    raise HTTPException(409, detail="路线切换请先生成变更方案，经差异核对、确认后执行")


@router.post("/versions")
def capture_version(
    project_id: int,
    body: PlanVersionInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.capture_version(project_id, body, actor))


@router.get("/versions/{version_id}")
def version(
    project_id: int,
    version_id: int,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(svc, svc.version(project_id, version_id, actor))


@router.post("/schedule-preview")
def schedule_preview(
    project_id: int,
    body: SchedulePreviewInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    from app.services.scheduling import SchedulingService, StaleSchedulePreview

    try:
        return SchedulingService(svc.db).preview(project_id, body, actor)
    except StaleSchedulePreview as exc:
        raise HTTPException(409, detail=exc.message) from exc


@router.put("/branch-groups/{group_id}")
def update_branch_group(
    project_id: int,
    group_id: int,
    body: BranchGroupUpdateInput,
    svc: PlanningService = Depends(service),
    actor: User = Depends(get_current_user),
) -> dict:
    return finish(
        svc,
        svc.put_branch_group(
            project_id,
            BranchGroupInput(**body.model_dump(exclude={"reason"})),
            actor,
            row_id=group_id,
            reason=body.reason,
        ),
    )
