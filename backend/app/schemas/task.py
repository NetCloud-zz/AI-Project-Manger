"""Task request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import TaskAiStatus, TaskLinkType, TaskStatus


class TaskPlanningFields(BaseModel):
    description: str | None = Field(default=None, max_length=10000)
    deliverable: str | None = Field(default=None, max_length=5000)
    acceptance_criteria: str | None = Field(default=None, max_length=5000)
    planned_duration_days: int | None = Field(default=None, ge=1, le=10000)
    remaining_duration_days: int | None = Field(default=None, ge=0, le=10000)
    actual_start_date: date | None = None
    actual_finish_date: date | None = None
    earliest_start_date: date | None = None
    fixed_start_date: date | None = None
    fixed_due_date: date | None = None
    calendar_id: int | None = None
    milestone_id: int | None = None
    task_group_id: int | None = None


class TaskBase(TaskPlanningFields):
    task_name: str = Field(min_length=1, max_length=300)
    owner_id: int
    due_date: date | None = None


class TaskCreate(TaskBase):
    start_date: date | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    status: TaskStatus = TaskStatus.TODO
    work_stream: str | None = Field(default=None, max_length=120)


class TaskUpdate(TaskPlanningFields):
    model_config = ConfigDict(extra="forbid")

    task_name: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: int | None = None
    start_date: date | None = None
    due_date: date | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    status: TaskStatus | None = None
    work_stream: str | None = Field(default=None, max_length=120)
    # Optimistic concurrency: when set, must match the current task.version.
    expected_version: int | None = Field(default=None, ge=1)


class TaskDeleteRequest(BaseModel):
    """Hard-delete a task. A written reason is mandatory and audited."""

    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("reason is required")
        return cleaned


class TaskOwnerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str


class TaskProjectBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_code: str
    project_name: str


class TaskResponse(TaskPlanningFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    task_name: str
    work_stream: str | None
    owner_id: int
    start_date: date | None
    due_date: date | None
    progress_percent: int | None
    status: TaskStatus
    ai_status: TaskAiStatus | None
    ai_risk_level: TaskAiStatus | None
    completed_at: datetime | None
    branch_option_id: int | None = None
    branch_root_id: int | None = None
    branch_label: str | None = None
    is_active_branch: bool = True
    version: int = 1
    created_at: datetime
    updated_at: datetime
    owner: TaskOwnerBrief | None = None
    project: TaskProjectBrief | None = None


class TaskBranchCreate(BaseModel):
    """Spawn an alternative path from an existing task (e.g. switch compound)."""

    task_name: str = Field(min_length=1, max_length=300)
    branch_label: str = Field(min_length=1, max_length=80)
    owner_id: int | None = None
    start_date: date | None = None
    due_date: date | None = None
    work_stream: str | None = Field(default=None, max_length=120)
    activate: bool = False
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("A meaningful branch change reason is required")
        return value


class TaskBranchActivate(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("A meaningful branch change reason is required")
        return value


class TaskLinkCreate(BaseModel):
    lag_days: int = Field(default=0, ge=0, le=10000)
    source_id: int
    target_id: int
    link_type: TaskLinkType = TaskLinkType.FINISH_TO_START


class TaskLinkUpdate(BaseModel):
    lag_days: int | None = Field(default=None, ge=0, le=10000)
    link_type: TaskLinkType


class TaskLinkResponse(BaseModel):
    lag_days: int = 0
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    source_id: int
    target_id: int
    link_type: TaskLinkType


class ProjectGanttResponse(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    target_date: date | None
    editable: bool
    tasks: list[TaskResponse]
    links: list[TaskLinkResponse]


class MyTasksPage(BaseModel):
    """Server-paged /tasks/my response."""

    items: list[TaskResponse]
    total: int
    page: int
    page_size: int
