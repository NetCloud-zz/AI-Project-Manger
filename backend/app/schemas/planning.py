"""Strict inputs for S1 planning editors."""

from __future__ import annotations

from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MemberInput(PlanningInput):
    role: Literal["CONTRIBUTOR", "OBSERVER"] = "CONTRIBUTOR"
    receive_notifications: bool = True
    is_active: bool = True


class ParticipantInput(PlanningInput):
    user_id: int
    role: Literal["COLLABORATOR", "WATCHER"] = "COLLABORATOR"


class ParticipantsInput(PlanningInput):
    participants: list[ParticipantInput] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_users(self) -> ParticipantsInput:
        if len({item.user_id for item in self.participants}) != len(self.participants):
            raise ValueError("Duplicate task participant")
        return self


class CalendarInput(PlanningInput):
    name: str = Field(min_length=1, max_length=120)
    timezone: str = "Asia/Shanghai"
    weekdays: list[int] = Field(min_length=1, max_length=7)
    exceptions: dict[date, bool] = Field(default_factory=dict, max_length=1000)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value) or len(set(value)) != len(value):
            raise ValueError("Weekdays must be unique integers 0 (Monday) through 6 (Sunday)")
        return sorted(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class MilestoneInput(PlanningInput):
    name: str = Field(min_length=1, max_length=200)
    deliverable: str | None = Field(default=None, max_length=5000)
    acceptance_criteria: str | None = Field(default=None, max_length=5000)
    target_date: date | None = None
    owner_id: int | None = None
    status: Literal["PLANNED", "ACHIEVED", "CANCELLED"] = "PLANNED"
    achieved_date: date | None = None

    @model_validator(mode="after")
    def achievement(self) -> MilestoneInput:
        if (self.status == "ACHIEVED") != (self.achieved_date is not None):
            raise ValueError("Only an achieved milestone must have achieved_date")
        return self


class TaskGroupInput(PlanningInput):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None


class BranchGroupInput(PlanningInput):
    name: str = Field(min_length=1, max_length=200)
    entry_task_id: int | None = None
    exit_task_id: int | None = None


class BranchGroupUpdateInput(BranchGroupInput):
    reason: str = Field(min_length=2, max_length=2000)


class BranchOptionInput(PlanningInput):
    name: str = Field(min_length=1, max_length=120)
    task_ids: list[int] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("task_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Duplicate task IDs")
        return value


class BranchSelectInput(PlanningInput):
    option_id: int
    expected_selected_option_id: int | None = None
    reason: str = Field(min_length=2, max_length=2000)


class PlanVersionInput(PlanningInput):
    reason: str = Field(min_length=2, max_length=2000)
    expected_latest_version: int = Field(ge=0)
