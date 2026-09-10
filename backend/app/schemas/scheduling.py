"""S2 preview inputs. Actual execution records and statuses are never patchable."""

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.planning import PlanningInput


class ScheduleTaskPatch(PlanningInput):
    task_id: int
    start_date: date | None = None
    due_date: date | None = None
    planned_duration_days: int | None = Field(default=None, ge=1, le=10000)
    remaining_duration_days: int | None = Field(default=None, ge=0, le=10000)
    earliest_start_date: date | None = None
    fixed_start_date: date | None = None
    fixed_due_date: date | None = None


class ScheduleLinkInput(PlanningInput):
    source_id: int
    target_id: int
    link_type: Literal[
        "FINISH_TO_START", "START_TO_START", "FINISH_TO_FINISH", "START_TO_FINISH"
    ] = "FINISH_TO_START"
    lag_days: int = Field(default=0, ge=0, le=10000)


class ScheduleSelection(PlanningInput):
    group_id: int
    option_id: int


class SchedulePreviewInput(PlanningInput):
    as_of: date | None = None
    mode: Literal["preserve_dates", "earliest"] = "preserve_dates"
    changes: list[ScheduleTaskPatch] = Field(default_factory=list, max_length=1000)
    links: list[ScheduleLinkInput] | None = Field(default=None, max_length=5000)
    selections: list[ScheduleSelection] = Field(default_factory=list, max_length=200)
    project_target_date: date | None = None
    expected_snapshot_token: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def unique_changes(self) -> "SchedulePreviewInput":
        if len({change.task_id for change in self.changes}) != len(self.changes):
            raise ValueError("Duplicate task changes")
        if len({selection.group_id for selection in self.selections}) != len(self.selections):
            raise ValueError("Duplicate branch selections")
        return self
