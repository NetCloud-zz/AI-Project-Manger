"""AIRun lifecycle helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.ai_run import AIRun, AIRunStatus, AIRunType
from app.repositories.agent_memory import AIRunRepository

USER_FACING_FAILURE = "AI 分析失败，请稍后重试"
USER_FACING_DISABLED = "LLM 未启用，已跳过 AI 分析"


class AIRunService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AIRunRepository(db)

    def create_queued(
        self,
        *,
        run_type: AIRunType,
        resource_type: str,
        resource_id: str | int,
        created_by: int | None = None,
        model: str | None = None,
    ) -> AIRun:
        run = AIRun(
            run_type=run_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            status=AIRunStatus.QUEUED,
            created_by=created_by,
            model=model,
            user_message=None,
        )
        return self.repo.add(run)

    def mark_running(self, run_id: int, *, model: str | None = None) -> AIRun | None:
        run = self.repo.get_by_id(run_id)
        if run is None:
            return None
        run.status = AIRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        if model:
            run.model = model
        return self.repo.save(run)

    def mark_succeeded(self, run_id: int) -> AIRun | None:
        run = self.repo.get_by_id(run_id)
        if run is None:
            return None
        run.status = AIRunStatus.SUCCEEDED
        run.completed_at = datetime.now(UTC)
        run.error_code = None
        run.user_message = None
        return self.repo.save(run)

    def mark_failed(self, run_id: int, *, error_code: str) -> AIRun | None:
        run = self.repo.get_by_id(run_id)
        if run is None:
            return None
        run.status = AIRunStatus.FAILED
        run.completed_at = datetime.now(UTC)
        run.error_code = error_code[:64]
        run.user_message = USER_FACING_FAILURE
        return self.repo.save(run)

    def mark_disabled(self, run_id: int) -> AIRun | None:
        run = self.repo.get_by_id(run_id)
        if run is None:
            return None
        run.status = AIRunStatus.DISABLED
        run.completed_at = datetime.now(UTC)
        run.error_code = "llm_disabled"
        run.user_message = USER_FACING_DISABLED
        return self.repo.save(run)

    def get(self, run_id: int) -> AIRun | None:
        return self.repo.get_by_id(run_id)

    def latest(
        self,
        *,
        resource_type: str,
        resource_id: str | int,
        run_type: AIRunType | None = None,
    ) -> AIRun | None:
        return self.repo.latest_for_resource(
            resource_type=resource_type,
            resource_id=str(resource_id),
            run_type=run_type,
        )
