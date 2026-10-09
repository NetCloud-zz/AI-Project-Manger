"""Daily sequential business codes for projects and tasks.

Formats (business timezone date as YYYYMMDD):
- Project: ``P{YYYYMMDD}-001`` (e.g. P20260911-001)
- Task: ``T{YYYYMMDD}-001`` (e.g. T20260911-001)

When the caller omits a code (or passes a placeholder such as 待定/自动),
allocate the next free sequence for today.
"""

from __future__ import annotations

import re
import zlib
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task
from app.services.business_clock import BusinessClock

Kind = Literal["project", "task"]

_PREFIX = {"project": "P", "task": "T"}
_PLACEHOLDER = re.compile(
    r"^(?:待定|待填|自动|自动生成|系统生成|tbd|auto|n/?a|none)?$",
    re.IGNORECASE,
)


def is_blank_or_placeholder_code(value: str | None) -> bool:
    if value is None:
        return True
    return bool(_PLACEHOLDER.match(str(value).strip()))


def day_stem(kind: Kind, *, clock: BusinessClock | None = None) -> str:
    today = (clock or BusinessClock()).today()
    return f"{_PREFIX[kind]}{today.strftime('%Y%m%d')}-"


def _lock(db: Session, stem: str) -> None:
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        key = zlib.crc32(stem.encode("utf-8")) & 0x7FFFFFFF
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _max_sequence(db: Session, kind: Kind, stem: str) -> int:
    column = Project.project_code if kind == "project" else Task.task_code
    stmt = select(column).where(column.like(f"{stem}%"))
    max_n = 0
    for code in db.scalars(stmt).all():
        if not code or not code.startswith(stem):
            continue
        suffix = code[len(stem) :]
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return max_n


def allocate_code(
    db: Session,
    kind: Kind,
    *,
    clock: BusinessClock | None = None,
    count: int = 1,
) -> list[str]:
    """Reserve ``count`` sequential codes for today (same stem).

    Codes are tracked on ``session.info`` until commit so multiple allocates
    in one transaction do not collide before rows are flushed.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    stem = day_stem(kind, clock=clock)
    _lock(db, stem)
    cache_key = f"entity_codes:{stem}"
    reserved: list[str] = db.info.setdefault(cache_key, [])
    max_n = _max_sequence(db, kind, stem)
    for code in reserved:
        suffix = code[len(stem) :] if code.startswith(stem) else ""
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    start = max_n + 1
    width = 3 if start + count - 1 < 1000 else len(str(start + count - 1))
    codes = [f"{stem}{index:0{width}d}" for index in range(start, start + count)]
    reserved.extend(codes)
    return codes


def allocate_project_code(db: Session, *, clock: BusinessClock | None = None) -> str:
    return allocate_code(db, "project", clock=clock, count=1)[0]


def allocate_task_code(db: Session, *, clock: BusinessClock | None = None) -> str:
    return allocate_code(db, "task", clock=clock, count=1)[0]


def allocate_task_codes(
    db: Session, count: int, *, clock: BusinessClock | None = None
) -> list[str]:
    return allocate_code(db, "task", clock=clock, count=count)


def resolve_project_code(db: Session, provided: str | None) -> str:
    if is_blank_or_placeholder_code(provided):
        return allocate_project_code(db)
    return str(provided).strip().upper()
