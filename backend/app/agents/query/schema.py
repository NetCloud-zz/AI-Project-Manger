"""Agent Query DSL — whitelist-only filters; never string-concatenated SQL."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_QUERY_LIMIT = 200
DEFAULT_QUERY_LIMIT = 50

FilterOp = Literal[
    "eq",
    "ne",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "before",
    "after",
    "between",
    "contains",
    "is_null",
]


class QueryFilter(BaseModel):
    field: str
    op: FilterOp
    value: Any = None


class QuerySort(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class QueryAggregate(BaseModel):
    function: Literal["count", "sum", "avg", "min", "max"]
    field: str
    alias: str | None = None


class AgentQueryRequest(BaseModel):
    filters: list[QueryFilter] = Field(default_factory=list)
    sort: list[QuerySort] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregates: list[QueryAggregate] = Field(default_factory=list)
    limit: int = DEFAULT_QUERY_LIMIT
    offset: int = 0

    @field_validator("limit")
    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return max(1, min(int(value), MAX_QUERY_LIMIT))

    @field_validator("offset")
    @classmethod
    def nonneg_offset(cls, value: int) -> int:
        return max(0, int(value))
