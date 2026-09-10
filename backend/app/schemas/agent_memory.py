"""Schemas for AgentMemory."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.agent_memory import MemoryScope, MemoryType


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    scope: MemoryScope = MemoryScope.USER
    memory_type: MemoryType = MemoryType.PREFERENCE
    project_id: int | None = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content cannot be blank")
        return cleaned


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1, max_length=2000)
    memory_type: MemoryType | None = None
    is_active: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_nulls(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in ("content", "is_active", "memory_type"):
            if key in data and data[key] is None:
                raise ValueError(f"{key} cannot be null")
        return data

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content cannot be blank")
        return cleaned


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    project_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
