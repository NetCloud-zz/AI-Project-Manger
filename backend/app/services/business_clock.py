"""Business-timezone clock and relative date presets for the project assistant.

Date-typed fields (due dates, week ranges) use Asia/Shanghai by default.
Timestamps remain stored in UTC; convert to business-day boundaries here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings

DEFAULT_BUSINESS_TZ = "Asia/Shanghai"


class DatePreset(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    THIS_WEEK = "this_week"
    NEXT_WEEK = "next_week"
    NEXT_7_DAYS = "next_7_days"


@dataclass(frozen=True)
class DateRange:
    """Inclusive calendar-day range in the business timezone."""

    start: date
    end: date
    preset: DatePreset | None = None
    timezone: str = DEFAULT_BUSINESS_TZ

    def as_dict(self) -> dict[str, str | None]:
        return {
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "preset": self.preset.value if self.preset else None,
            "business_timezone": self.timezone,
            "inclusive": True,
        }


class BusinessClock:
    """Injectable business clock — never use UTC calendar dates for due-day logic."""

    def __init__(
        self,
        *,
        timezone: str | None = None,
        now: datetime | None = None,
        settings: Settings | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self.timezone = timezone or getattr(cfg, "SCHEDULER_TIMEZONE", DEFAULT_BUSINESS_TZ)
        self._zone = ZoneInfo(self.timezone)
        self._fixed_now = now

    def now(self) -> datetime:
        if self._fixed_now is not None:
            return self._fixed_now.astimezone(self._zone)
        return datetime.now(self._zone)

    def today(self) -> date:
        return self.now().date()

    def resolve_preset(self, preset: DatePreset | str) -> DateRange:
        value = DatePreset(preset) if not isinstance(preset, DatePreset) else preset
        today = self.today()
        if value is DatePreset.TODAY:
            return DateRange(today, today, value, self.timezone)
        if value is DatePreset.TOMORROW:
            day = today + timedelta(days=1)
            return DateRange(day, day, value, self.timezone)
        if value is DatePreset.THIS_WEEK:
            # Monday–Sunday of the current week.
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return DateRange(start, end, value, self.timezone)
        if value is DatePreset.NEXT_WEEK:
            this_monday = today - timedelta(days=today.weekday())
            start = this_monday + timedelta(days=7)
            end = start + timedelta(days=6)
            return DateRange(start, end, value, self.timezone)
        if value is DatePreset.NEXT_7_DAYS:
            # Inclusive: today through today+6 (seven calendar days).
            return DateRange(today, today + timedelta(days=6), value, self.timezone)
        msg = f"Unknown date preset: {preset}"
        raise ValueError(msg)

    def resolve_range(
        self,
        *,
        date_preset: str | DatePreset | None = None,
        due_from: date | str | None = None,
        due_to: date | str | None = None,
    ) -> DateRange | None:
        if date_preset:
            return self.resolve_preset(date_preset)
        start = _as_date(due_from)
        end = _as_date(due_to)
        if start is None and end is None:
            return None
        if start is None:
            start = end
        if end is None:
            end = start
        assert start is not None and end is not None
        if start > end:
            msg = "due_from cannot be later than due_to"
            raise ValueError(msg)
        return DateRange(start, end, None, self.timezone)


def _as_date(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])
