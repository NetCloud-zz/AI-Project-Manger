"""Request bodies for risk events and advice records."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Closing a risk requires saying why; a bare click proves nothing.
    resolution: str = Field(min_length=2, max_length=2000)


class RiskRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Running the schedule engine is the expensive part; make it a choice.
    with_forecast: bool = True


class AdoptedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    owner_id: int | None = None
    task_id: int | None = None
    due_date: date | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"] = "MEDIUM"


class AdviceAdoptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)
    actions: list[AdoptedAction] = Field(default_factory=list, max_length=20)


class AdviceRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=2, max_length=2000)


class AdviceLinkProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1, max_length=36)


class AdviceEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["EFFECTIVE", "PARTIAL", "INEFFECTIVE"]
    #: Whether the problem went away, recorded apart from whether the advice was good.
    issue_resolved: bool
    note: str | None = Field(default=None, max_length=2000)


class RiskEventResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    project_id: int
    event_type: str
    level: str
    status: str
    title: str


class AdviceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    issue_id: int
    project_id: int
    version: int
    status: str
    content: dict[str, Any]
