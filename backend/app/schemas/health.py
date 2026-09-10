"""Response models for the health endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ComponentStatus = Literal["up", "down", "not_configured"]


class DependencyHealth(BaseModel):
    status: ComponentStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    version: str
    environment: str
    dependencies: dict[str, DependencyHealth] = Field(default_factory=dict)
