"""S3 requests never accept a caller-supplied confirmer or actual execution facts."""

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.planning import PlanningInput
from app.schemas.scheduling import SchedulePreviewInput, ScheduleTaskPatch
from app.schemas.task import TaskCreate


class ProposalTaskPatch(ScheduleTaskPatch):
    task_name: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: int | None = None
    work_stream: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    deliverable: str | None = Field(default=None, max_length=5000)
    acceptance_criteria: str | None = Field(default=None, max_length=5000)


class NewTaskData(TaskCreate):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def not_started(self) -> "NewTaskData":
        if self.status != "TODO" or self.actual_start_date or self.actual_finish_date:
            raise ValueError("New proposal tasks must be not-started tasks without actual dates")
        return self


class ProposedNewTask(PlanningInput):
    client_id: int = Field(le=-1)
    task: NewTaskData


class ChangeRequest(SchedulePreviewInput):
    changes: list[ProposalTaskPatch] = Field(default_factory=list, max_length=1000)  # type: ignore[assignment]
    new_tasks: list[ProposedNewTask] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_new_tasks(self) -> "ChangeRequest":
        if len({task.client_id for task in self.new_tasks}) != len(self.new_tasks):
            raise ValueError("Duplicate new task client IDs")
        if any(change.task_id < 1 for change in self.changes):
            raise ValueError("Edit new tasks through new_tasks, not changes")
        return self


class ProposalSource(PlanningInput):
    kind: Literal["ISSUE", "PROGRESS"]
    id: int


class ProposalCreate(PlanningInput):
    reason: str = Field(min_length=2, max_length=2000)
    change: ChangeRequest
    source: ProposalSource | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


class ProposalEdit(PlanningInput):
    reason: str = Field(min_length=2, max_length=2000)
    change: ChangeRequest
    expected_revision: int = Field(ge=1)


class ProposalRevision(PlanningInput):
    expected_revision: int = Field(ge=1)


class ProposalConfirmation(ProposalRevision):
    digest: str = Field(min_length=64, max_length=64)


class ProposalApply(ProposalConfirmation):
    idempotency_key: str = Field(min_length=8, max_length=100)
