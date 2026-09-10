"""Progress update request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskAiStatus


class ProgressSubmit(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    mark_completed: bool = False


class ProgressUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    user_id: int
    raw_content: str
    summary: str | None
    progress_percent: int | None
    ai_status: TaskAiStatus | None
    risk_detected: bool | None
    ai_analysis_failed: bool
    created_at: datetime


class RecentProgressItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    task_name: str
    user_id: int
    user_name: str
    raw_content: str
    summary: str | None
    created_at: datetime
