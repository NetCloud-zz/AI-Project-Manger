"""BusinessClock calendar days follow BUSINESS_TZ, not UTC date.today()."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.business_clock import BusinessClock, DatePreset


def test_today_uses_business_timezone_not_utc_calendar():
    # 2026-09-10 16:30 UTC → already 2026-09-11 in Asia/Shanghai
    fixed = datetime(2026, 9, 10, 16, 30, tzinfo=UTC)
    clock = BusinessClock(timezone="Asia/Shanghai", now=fixed)
    assert clock.today().isoformat() == "2026-09-11"
    assert clock.timezone == "Asia/Shanghai"


def test_resolve_preset_today_and_tomorrow():
    fixed = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)  # Shanghai still 2026-09-10
    clock = BusinessClock(timezone="Asia/Shanghai", now=fixed)
    today = clock.resolve_preset(DatePreset.TODAY)
    tomorrow = clock.resolve_preset(DatePreset.TOMORROW)
    assert today.start.isoformat() == "2026-09-10"
    assert tomorrow.start.isoformat() == "2026-09-11"
    assert tomorrow.end == tomorrow.start
