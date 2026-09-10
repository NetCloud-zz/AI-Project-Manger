"""Action item request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.action_item import ActionItemPriority, ActionItemStatus


class ActionItemUserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str


class ActionItemTaskBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_name: str


class ActionItemIssueBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str


class ActionItemProjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_code: str
    project_name: str


class ActionItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    owner_id: int | None = None
    task_id: int | None = None
    issue_id: int | None = None
    due_date: date | None = None
    status: ActionItemStatus = ActionItemStatus.OPEN
    priority: ActionItemPriority = ActionItemPriority.MEDIUM


class ActionItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    owner_id: int | None = None
    task_id: int | None = None
    issue_id: int | None = None
    due_date: date | None = None
    status: ActionItemStatus | None = None
    priority: ActionItemPriority | None = None


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    task_id: int | None
    issue_id: int | None
    owner_id: int | None
    created_by: int
    title: str
    description: str | None
    due_date: date | None
    status: ActionItemStatus
    priority: ActionItemPriority
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    owner: ActionItemUserBrief | None = None
    creator: ActionItemUserBrief | None = None
    task: ActionItemTaskBrief | None = None
    issue: ActionItemIssueBrief | None = None
    project: ActionItemProjectBrief | None = None
