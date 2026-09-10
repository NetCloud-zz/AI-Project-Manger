"""Progress update business logic."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.progress_update import ProgressUpdate
from app.models.task import TaskStatus
from app.models.user import User
from app.repositories.progress_update import ProgressUpdateRepository
from app.schemas.progress import ProgressSubmit
from app.schemas.task import TaskUpdate
from app.services.audit import AuditService
from app.services.exceptions import TaskNotFoundError
from app.services.task import TaskService


class ProgressService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ProgressUpdateRepository(db)
        self.tasks = TaskService(db)
        self.audit = AuditService(db)

    def submit_progress(
        self,
        task_id: int,
        data: ProgressSubmit,
        *,
        actor: User,
        ip_address: str | None = None,
    ) -> ProgressUpdate:
        task = self.tasks.get_task(task_id)
        progress = ProgressUpdate(
            task_id=task_id,
            user_id=actor.id,
            raw_content=data.content.strip(),
        )
        self.repo.add(progress)

        if data.mark_completed and task.status != TaskStatus.COMPLETED:
            self.tasks.update_task(
                task_id,
                TaskUpdate(status=TaskStatus.COMPLETED),
                actor=actor,
                allow_core_fields=False,
                ip_address=ip_address,
            )

        return self.repo.get_by_id(progress.id) or progress

    def get_progress(self, progress_id: int) -> ProgressUpdate | None:
        return self.repo.get_by_id(progress_id)

    def list_task_progress(self, task_id: int) -> list[ProgressUpdate]:
        if self.tasks.get_task(task_id) is None:
            raise TaskNotFoundError
        return self.repo.list_by_task(task_id)

    def list_recent_by_project(self, project_id: int, *, limit: int = 20) -> list[ProgressUpdate]:
        return self.repo.list_recent_by_project(project_id, limit=limit)

    def update_ai_fields(
        self,
        progress_id: int,
        *,
        summary: str | None = None,
        progress_percent: int | None = None,
        ai_status: str | None = None,
        risk_detected: bool | None = None,
        ai_analysis_failed: bool = False,
    ) -> ProgressUpdate:
        progress = self.repo.get_by_id(progress_id)
        if progress is None:
            msg = "Progress update not found"
            raise TaskNotFoundError(msg)
        if summary is not None:
            progress.summary = summary
        if progress_percent is not None:
            progress.progress_percent = progress_percent
        if ai_status is not None:
            from app.models.task import TaskAiStatus

            progress.ai_status = TaskAiStatus(ai_status)
        if risk_detected is not None:
            progress.risk_detected = risk_detected
        progress.ai_analysis_failed = ai_analysis_failed
        progress.updated_at = datetime.now(UTC)
        return progress
