"""Plan draft inputs. Drafts may be incomplete; publishing may not."""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from app.models.task import TaskLinkType
from app.schemas.planning import PlanningInput


class DraftMilestone(PlanningInput):
    client_id: int = Field(le=-1)
    name: str = Field(min_length=1, max_length=200)
    target_date: date | None = None
    deliverable: str | None = Field(default=None, max_length=5000)
    acceptance_criteria: str | None = Field(default=None, max_length=5000)


class DraftTask(PlanningInput):
    client_id: int = Field(le=-1)
    task_name: str = Field(min_length=1, max_length=300)
    owner_id: int | None = None
    work_stream: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    deliverable: str | None = Field(default=None, max_length=5000)
    acceptance_criteria: str | None = Field(default=None, max_length=5000)
    start_date: date | None = None
    due_date: date | None = None
    planned_duration_days: int | None = Field(default=None, ge=1, le=10000)
    earliest_start_date: date | None = None
    fixed_start_date: date | None = None
    fixed_due_date: date | None = None
    milestone_client_id: int | None = Field(default=None, le=-1)
    #: Where the estimate came from, e.g. "用户口述" / "模板" / "AI 估算".
    estimate_basis: str | None = Field(default=None, max_length=500)


class DraftLink(PlanningInput):
    source_client_id: int = Field(le=-1)
    target_client_id: int = Field(le=-1)
    link_type: TaskLinkType = TaskLinkType.FINISH_TO_START
    lag_days: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def distinct(self) -> DraftLink:
        if self.source_client_id == self.target_client_id:
            raise ValueError("依赖的前后任务不能相同")
        return self


class DraftProject(PlanningInput):
    project_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    project_name: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=5000)
    owner_id: int | None = None
    owner_ids: list[int] | None = Field(default=None, min_length=1, max_length=20)
    start_date: date | None = None
    target_date: date | None = None


class PlanDraftContent(PlanningInput):
    project: DraftProject
    tasks: list[DraftTask] = Field(default_factory=list, max_length=500)
    links: list[DraftLink] = Field(default_factory=list, max_length=2000)
    milestones: list[DraftMilestone] = Field(default_factory=list, max_length=100)
    #: Stated assumptions behind the estimates; kept so reviewers can challenge them.
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    #: Questions the draft still needs answered before it can be published.
    open_questions: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_client_ids(self) -> PlanDraftContent:
        ids = [task.client_id for task in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("任务临时编号重复")
        milestone_ids = [item.client_id for item in self.milestones]
        if len(set(milestone_ids)) != len(milestone_ids):
            raise ValueError("里程碑临时编号重复")
        pairs = {(link.source_client_id, link.target_client_id) for link in self.links}
        if len(pairs) != len(self.links):
            raise ValueError("依赖关系重复")
        return self


class PlanDraftCreate(PlanningInput):
    title: str = Field(min_length=1, max_length=200)
    content: PlanDraftContent
    idempotency_key: str = Field(min_length=8, max_length=100)


class PlanDraftUpdate(PlanningInput):
    title: str = Field(min_length=1, max_length=200)
    content: PlanDraftContent
    expected_revision: int = Field(ge=1)


class PlanDraftRevision(PlanningInput):
    expected_revision: int = Field(ge=1)


class PlanDraftPublish(PlanDraftRevision):
    digest: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=100)
