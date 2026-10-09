"""Project assistant mutation contract. Copyright 2024–2026 Jack Zhang.

Reasons are supplied by the caller, never invented by the service. Presence of a
protected field (including clearing it) requires a reason before any write.
"""

from __future__ import annotations

from typing import Any

from app.services.exceptions import DomainValidationError

TASK_PLAN_FIELDS = frozenset(
    {
        "start_date",
        "due_date",
        "actual_start_date",
        "actual_finish_date",
        "earliest_start_date",
        "fixed_start_date",
        "fixed_due_date",
        "planned_duration_days",
        "remaining_duration_days",
        "calendar_id",
        "work_stream",
        "task_group_id",
        "branch_option_id",
        "branch_root_id",
        "branch_label",
        "is_active_branch",
    }
)
REASON_FIELDS = {
    "update_project": frozenset({"goal", "start_date", "target_date"}),
    "update_task": TASK_PLAN_FIELDS,
    "update_action_item": frozenset({"due_date"}),
}
ALWAYS_REASON = frozenset(
    {
        "reschedule_task",
        "create_task_branch",
        "activate_task_branch",
        "propose_change",
        "update_project_plan_draft",
    }
)


def require_change_reason(name: str, args: dict[str, Any]) -> str | None:
    if name not in ALWAYS_REASON and not REASON_FIELDS.get(name, frozenset()).intersection(args):
        return None
    value = args.get("change_reason", args.get("reason"))
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 2000:
        raise DomainValidationError(
            "日期、项目方向或任务分支变更必须提供 2–2000 字的修改原因"
            "（change_reason；分支/变更方案使用 reason），不能由助手编造。"
        )
    return value.strip()


def audit_change_reason(
    db: Any, actor: Any, name: str, resource_id: Any, args: dict[str, Any]
) -> None:
    reason = require_change_reason(name, args)
    if reason is None:
        return
    from app.services.audit import AuditService

    AuditService(db).record(
        action="agent.change_reason",
        resource_type=name,
        resource_id=str(resource_id),
        user_id=actor.id,
        new_value={
            "change_reason": reason,
            "fields": sorted(REASON_FIELDS.get(name, frozenset()).intersection(args)),
        },
    )
