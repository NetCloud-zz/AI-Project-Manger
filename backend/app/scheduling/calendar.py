"""Working-day slots: start is inclusive, finish is the next slot boundary."""

from bisect import bisect_left, bisect_right
from datetime import date, timedelta


class CalendarRangeError(ValueError):
    pass


class WorkingCalendar:
    MAX_DAYS = 73_050  # Explicit bounded horizon, about 200 years.

    def __init__(self, origin: date, weekdays: list[int], exceptions: dict[str, bool]) -> None:
        if (
            not weekdays
            or len(set(weekdays)) != len(weekdays)
            or any(d not in range(7) for d in weekdays)
        ):
            raise ValueError("工作周必须包含不重复的 0～6")
        self.weekdays = frozenset(weekdays)
        self.exceptions = {date.fromisoformat(key): value for key, value in exceptions.items()}
        self.origin = max(date.min, origin - timedelta(days=min(14, origin.toordinal() - 1)))
        end = min(date.max.toordinal(), self.origin.toordinal() + self.MAX_DAYS)
        self.days = [
            date.fromordinal(ordinal)
            for ordinal in range(self.origin.toordinal(), end + 1)
            if self.is_workday(date.fromordinal(ordinal))
        ]
        if not self.days:
            raise CalendarRangeError("计算范围内没有工作日")

    def is_workday(self, day: date) -> bool:
        return self.exceptions.get(day, day.weekday() in self.weekdays)

    def _check(self, day: date) -> None:
        if day < self.origin or day > self.days[-1]:
            raise CalendarRangeError("日期超出排期计算范围")

    def start(self, day: date) -> int:
        """First workday on or after day; historical actual dates remain separately stored."""
        self._check(day)
        return bisect_left(self.days, day)

    def finish(self, day: date) -> int:
        """End boundary through day, including an actual finish on a non-working day."""
        self._check(day)
        return bisect_right(self.days, day)

    def start_date(self, tick: int) -> date:
        if tick < 0 or tick >= len(self.days):
            raise CalendarRangeError("工期超出排期计算范围")
        return self.days[tick]

    def finish_date(self, tick: int) -> date:
        if tick <= 0 or tick > len(self.days):
            raise CalendarRangeError("工期超出排期计算范围")
        return self.days[tick - 1]

    def delta(self, before: date, after: date) -> int:
        return self.finish(after) - self.finish(before)
