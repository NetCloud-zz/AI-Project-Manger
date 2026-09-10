"""Scheduler timezone helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def get_scheduler_timezone() -> ZoneInfo:
    return ZoneInfo(settings.SCHEDULER_TIMEZONE)


def scheduler_today() -> date:
    return datetime.now(get_scheduler_timezone()).date()


def day_bounds(on_date: date, tz: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    """Return [start, end) UTC datetimes for a calendar day in the scheduler TZ."""
    tz = tz or get_scheduler_timezone()
    start_local = datetime.combine(on_date, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
