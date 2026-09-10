"""Project request/response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.project import ProjectRiskLevel, ProjectStatus


class ProjectBase(BaseModel):
    project_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    project_name: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=5000)
    owner_id: int
    start_date: date | None = None
    target_date: date | None = None


class ProjectCreate(ProjectBase):
    status: ProjectStatus = ProjectStatus.ACTIVE
    risk_level: ProjectRiskLevel = ProjectRiskLevel.NORMAL
    # Additional owners; every id in the set (including owner_id) has equal authority.
    owner_ids: list[int] | None = Field(default=None, min_length=1)


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=5000)
    owner_id: int | None = None
    status: ProjectStatus | None = None
    risk_level: ProjectRiskLevel | None = None
    # Full owner set. All listed users are equal owners; order is not significant.
    owner_ids: list[int] | None = Field(default=None, min_length=1)


class ProjectScheduleUpdate(BaseModel):
    """Change project start / target dates. A written reason is mandatory."""

    start_date: date | None = None
    target_date: date | None = None
    change_reason: str = Field(min_length=2, max_length=2000)

    @model_validator(mode="after")
    def require_at_least_one_date(self) -> ProjectScheduleUpdate:
        if not {"start_date", "target_date"}.intersection(self.model_fields_set):
            msg = "Provide start_date and/or target_date"
            raise ValueError(msg)
        return self

    @field_validator("change_reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("change_reason is required")
        return cleaned


class ProjectDeleteRequest(BaseModel):
    """Hard-delete a project. A written reason is mandatory and audited."""

    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("reason is required")
        return cleaned


class ProjectOwnersUpdate(BaseModel):
    """Replace the full set of project owners. At least one id required."""

    owner_ids: list[int] = Field(min_length=1)

    @field_validator("owner_ids")
    @classmethod
    def dedupe(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for item in value:
            if item not in seen:
                seen.add(item)
                out.append(item)
        if not out:
            raise ValueError("At least one owner is required")
        return out


class ProjectOwnerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_code: str
    project_name: str
    goal: str | None
    owner_id: int
    start_date: date | None = None
    target_date: date | None
    status: ProjectStatus
    risk_level: ProjectRiskLevel
    created_at: datetime
    updated_at: datetime
    owner: ProjectOwnerBrief | None = None
    owners: list[ProjectOwnerBrief] = Field(default_factory=list)
