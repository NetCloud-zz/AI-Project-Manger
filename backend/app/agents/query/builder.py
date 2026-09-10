"""Apply whitelist Query DSL filters to in-memory entity dicts (post ORM + RBAC).

SQLAlchemy expressions are built only from mapped columns in the whitelist —
never from raw user field strings via getattr(Model, user_input).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.agents.query.fields import ENTITY_FIELDS
from app.agents.query.schema import AgentQueryRequest, QueryFilter
from app.services.business_clock import BusinessClock


def _resolve_attr(row: Any, path: str) -> Any:
    current = row
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    if hasattr(current, "value"):
        try:
            return current.value
        except Exception:  # noqa: BLE001
            return current
    return current


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def match_filter(row: Any, filt: QueryFilter, *, fields: dict[str, str], today: date) -> bool:
    if fields.get(filt.field) == "__computed__":
        return _match_computed(row, filt, today=today, fields=fields)
    path = fields[filt.field]
    actual = _resolve_attr(row, path)
    op = filt.op
    expected = filt.value
    if op == "is_null":
        flag = bool(expected) if expected is not None else True
        return (actual is None) if flag else (actual is not None)
    if op == "eq":
        if isinstance(actual, date) or filt.field.endswith("date"):
            return _as_date(actual) == _as_date(expected)
        return actual == expected or str(actual) == str(expected)
    if op == "ne":
        return not match_filter(
            row, QueryFilter(field=filt.field, op="eq", value=expected), fields=fields, today=today
        )
    if op == "in":
        return actual in expected or str(actual) in {str(v) for v in expected}
    if op == "not_in":
        return not match_filter(
            row, QueryFilter(field=filt.field, op="in", value=expected), fields=fields, today=today
        )
    if op == "contains":
        return expected is not None and str(expected).lower() in str(actual or "").lower()
    left = _as_date(actual) if filt.field.endswith("date") or "date" in filt.field else actual
    right = _as_date(expected) if isinstance(expected, str) and "date" in filt.field else expected
    if op in {"gt", "after"}:
        return left is not None and right is not None and left > right
    if op in {"gte"}:
        return left is not None and right is not None and left >= right
    if op in {"lt", "before"}:
        return left is not None and right is not None and left < right
    if op in {"lte"}:
        return left is not None and right is not None and left <= right
    if op == "between":
        low, high = expected[0], expected[1]
        if "date" in filt.field:
            left_d, low_d, high_d = _as_date(actual), _as_date(low), _as_date(high)
            return left_d is not None and low_d is not None and high_d is not None and low_d <= left_d <= high_d
        return actual is not None and low <= actual <= high
    return False


def _match_computed(row: Any, filt: QueryFilter, *, today: date, fields: dict[str, str]) -> bool:
    status = _resolve_attr(row, fields.get("status", "status"))
    due = _as_date(_resolve_attr(row, fields.get("due_date", "due_date")))
    completed = str(status) in {"COMPLETED", "CANCELLED"}
    is_overdue = bool(due and due < today and not completed)
    if filt.field == "is_overdue":
        want = bool(filt.value) if filt.op == "eq" else True
        return is_overdue if want else not is_overdue
    if filt.field == "days_overdue":
        days = (today - due).days if is_overdue and due else 0
        if filt.op == "eq":
            return days == int(filt.value)
        if filt.op in {"gt", "gte", "lt", "lte"}:
            return match_filter(
                {"days_overdue": days},
                QueryFilter(field="days_overdue", op=filt.op, value=filt.value),
                fields={"days_overdue": "days_overdue"},
                today=today,
            )
    return False


def apply_query(
    rows: list[Any],
    request: AgentQueryRequest,
    *,
    entity: str,
    clock: BusinessClock | None = None,
) -> dict[str, Any]:
    fields = ENTITY_FIELDS[entity]
    today = (clock or BusinessClock()).today()
    matched = [
        row
        for row in rows
        if all(match_filter(row, filt, fields=fields, today=today) for filt in request.filters)
    ]

    if request.aggregates or request.group_by:
        return _aggregate(matched, request, fields=fields, today=today)

    def sort_key(row: Any) -> tuple:
        keys = []
        for sort in request.sort:
            path = fields.get(sort.field, sort.field)
            value = _resolve_attr(row, path)
            keys.append(value is None)
            keys.append(value)
        return tuple(keys)

    if request.sort:
        reverse = request.sort[0].direction == "desc"
        matched = sorted(matched, key=sort_key, reverse=reverse)

    total = len(matched)
    page = matched[request.offset : request.offset + request.limit]
    return {
        "items": page,
        "total": total,
        "limit": request.limit,
        "offset": request.offset,
        "truncated": request.offset + len(page) < total,
    }


def _aggregate(
    rows: list[Any],
    request: AgentQueryRequest,
    *,
    fields: dict[str, str],
    today: date,
) -> dict[str, Any]:
    groups: dict[tuple, list[Any]] = {}
    if not request.group_by:
        groups[()] = rows
    else:
        for row in rows:
            key = tuple(_resolve_attr(row, fields[g]) for g in request.group_by)
            groups.setdefault(key, []).append(row)

    items = []
    for key, members in groups.items():
        item: dict[str, Any] = {
            request.group_by[i]: key[i] for i in range(len(request.group_by))
        }
        for agg in request.aggregates:
            alias = agg.alias or f"{agg.function}_{agg.field}"
            if agg.function == "count":
                item[alias] = len(members)
            else:
                values = []
                for member in members:
                    path = fields.get(agg.field, agg.field)
                    raw = _resolve_attr(member, path)
                    if raw is not None and not isinstance(raw, bool):
                        try:
                            values.append(float(raw))
                        except (TypeError, ValueError):
                            continue
                if not values:
                    item[alias] = None
                elif agg.function == "sum":
                    item[alias] = sum(values)
                elif agg.function == "avg":
                    item[alias] = sum(values) / len(values)
                elif agg.function == "min":
                    item[alias] = min(values)
                elif agg.function == "max":
                    item[alias] = max(values)
        items.append(item)

    if request.sort:
        sort = request.sort[0]
        items.sort(
            key=lambda row: (row.get(sort.field) is None, row.get(sort.field)),
            reverse=sort.direction == "desc",
        )
    total = len(items)
    page = items[request.offset : request.offset + request.limit]
    return {
        "items": page,
        "total": total,
        "limit": request.limit,
        "offset": request.offset,
        "truncated": request.offset + len(page) < total,
        "aggregated": True,
    }
