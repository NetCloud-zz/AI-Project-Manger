"""Daily project summary API schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DailySummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    summary_date: date
    summary: str
    risk_summary: str
    next_action: str
    management_attention: str
    created_at: datetime
