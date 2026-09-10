"""Schemas for AIRun."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.ai_run import AIRunStatus, AIRunType


class AIRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_type: AIRunType
    resource_type: str
    resource_id: str
    status: AIRunStatus
    model: str | None
    error_code: str | None
    user_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
