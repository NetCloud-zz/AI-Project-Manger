"""Labels that mean “owner not chosen yet” (task may stay unassigned)."""

from __future__ import annotations

import re

PENDING_OWNER_LABELS = frozenset(
    {
        "待填写",
        "待定",
        "待补充",
        "未定",
        "未知",
        "未填写",
        "未指定",
        "待确认",
        "未指派",
        "tbd",
        "n/a",
        "na",
        "none",
    }
)

# Standalone project-field line, e.g. "负责人：待填写" — not "任务 —— 负责人待定".
_PROJECT_PENDING_OWNER_LINE = re.compile(
    r"(?m)^\s*负责人\s*[:：]\s*(?:待填写|待定|待补充|未定|未知|未填写|未指定|待确认|TBD)\s*$",
    re.IGNORECASE,
)


def is_pending_owner_label(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    if not text:
        return True
    return text.casefold() in PENDING_OWNER_LABELS


def has_project_pending_owner_line(source: str) -> bool:
    return bool(_PROJECT_PENDING_OWNER_LINE.search(source))
