"""Dashboard request/response schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectRiskLevel, ProjectStatus


class DashboardProjectItem(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    status: ProjectStatus
    risk_level: ProjectRiskLevel
    owner: str
    current_focus: str | None = None
    next_deadline: date | None = None


class ManagementAttentionItem(BaseModel):
    item_type: str = Field(
        description=(
            "ISSUE_CRITICAL | ISSUE_HIGH_STALE | TASK_DELAYED | "
            "TASK_STALE_PROGRESS | PROJECT_DELAYED"
        )
    )
    project_id: int
    project_code: str
    project_name: str
    summary: str
    resource_type: str
    resource_id: int


class DashboardResponse(BaseModel):
    project_total: int
    normal_count: int
    at_risk_count: int
    delayed_count: int
    project_items: list[DashboardProjectItem]
    management_attention_count: int


class PersonalDashboardResponse(BaseModel):
    """Minimal dashboard for members — task counts only."""

    model_config = ConfigDict(from_attributes=True)

    my_active_tasks: int
    my_overdue_tasks: int
