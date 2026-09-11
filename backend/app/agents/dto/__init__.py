"""Agent-facing DTOs — lean payloads for the LLM (Phase 1).

ORM / domain objects are never passed to the model; services still own rules.
"""

from __future__ import annotations

from typing import Any

_TASK_KEEP = frozenset(
    {
        "id",
        "task_name",
        "project_id",
        "project_code",
        "work_stream",
        "status",
        "progress_percent",
        "owner_id",
        "owner_name",
        "owner_username",
        "start_date",
        "due_date",
        "planned_due_date",
        "forecast_finish_date",
        "actual_finish_date",
        "ai_status",
        "ai_risk_level",
        "branch_label",
        "is_active_branch",
        "branch_root_id",
        "date_semantics",
        "version",
    }
)

_PROJECT_KEEP = frozenset(
    {
        "id",
        "project_code",
        "project_name",
        "goal",
        "owner_id",
        "owner_name",
        "owner_ids",
        "owners",
        "start_date",
        "target_date",
        "status",
        "risk_level",
    }
)

_ISSUE_KEEP = frozenset(
    {
        "id",
        "project_id",
        "project_code",
        "task_id",
        "title",
        "description",
        "severity",
        "status",
        "reported_by",
        "reported_by_name",
    }
)

_RISK_KEEP = frozenset(
    {
        "id",
        "project_id",
        "project_code",
        "task_id",
        "risk_type",
        "status",
        "severity",
        "title",
        "summary",
        "first_detected_at",
        "owner_id",
        "owner_name",
    }
)

_DROP_ALWAYS = frozenset(
    {
        "password",
        "password_hash",
        "secret",
        "token",
        "api_key",
        "permission_mask",
        "creator_ip",
        "deleted_at",
        "tenant_internal_id",
        "internal_flag",
    }
)


def _strip_dict(row: dict[str, Any], keep: frozenset[str] | None) -> dict[str, Any]:
    cleaned = {k: v for k, v in row.items() if k not in _DROP_ALWAYS}
    if keep is None:
        return cleaned
    return {k: v for k, v in cleaned.items() if k in keep or k == "card"}


def sanitize_agent_data(tool_name: str, data: Any) -> Any:
    """Reduce tool payloads before they are sent back to the LLM."""
    if data is None:
        return None
    if not isinstance(data, dict):
        return data

    # Preserve envelope-like business dicts that already use ok/action.
    payload = dict(data)
    card = payload.get("card")

    if tool_name in {
        "search_tasks",
        "list_my_tasks",
        "list_project_tasks",
        "list_delayed_tasks",
        "list_at_risk_tasks",
        "list_task_branches",
    }:
        items = payload.get("items")
        if isinstance(items, list):
            payload["items"] = [
                _strip_dict(item, _TASK_KEEP) if isinstance(item, dict) else item for item in items
            ]
        return payload

    if tool_name in {"get_project", "list_projects", "create_project", "update_project"}:
        if isinstance(payload.get("project"), dict):
            payload["project"] = _strip_dict(payload["project"], _PROJECT_KEEP)
            return _strip_dict(payload, _PROJECT_KEEP | {"ok", "action", "card", "project"})
        if "items" in payload and isinstance(payload["items"], list):
            payload["items"] = [
                _strip_dict(item, _PROJECT_KEEP) if isinstance(item, dict) else item
                for item in payload["items"]
            ]
            return payload
        return _strip_dict(payload, _PROJECT_KEEP | {"ok", "action", "card"})

    if tool_name == "get_task_progress":
        # Single-task lookups are historically flat; normalize to ``task`` so
        # command-plan $ref paths (e.g. ``t.task.id``) and write tools stay aligned.
        if isinstance(payload.get("task"), dict):
            payload["task"] = _strip_dict(payload["task"], _TASK_KEEP)
            return payload
        if payload.get("tasks") is not None:
            tasks = payload.get("tasks")
            if isinstance(tasks, list):
                payload["tasks"] = [
                    _strip_dict(item, _TASK_KEEP) if isinstance(item, dict) else item
                    for item in tasks
                ]
            return payload
        if "task_name" in payload or "id" in payload:
            found = payload.get("found", True)
            project = payload.get("project")
            lean_task = _strip_dict(payload, _TASK_KEEP)
            out: dict[str, Any] = {"found": found, "task": lean_task}
            if isinstance(project, dict):
                out["project"] = _strip_dict(project, _PROJECT_KEEP)
            return out
        return payload

    if tool_name in {
        "create_task",
        "update_task",
        "create_task_branch",
        "activate_task_branch",
    }:
        task = payload.get("task")
        if isinstance(task, dict):
            payload["task"] = _strip_dict(task, _TASK_KEEP)
        # Flat task payloads from some write tools.
        if "task_name" in payload or "due_date" in payload:
            base = _strip_dict(payload, _TASK_KEEP | {"ok", "action", "card", "effects"})
            if isinstance(card, dict):
                base["card"] = card
            return base
        if isinstance(card, dict):
            payload["card"] = card
        return payload

    if tool_name in {"list_open_issues", "create_issue", "update_issue", "get_issue_evidence"}:
        if isinstance(payload.get("issue"), dict):
            payload["issue"] = _strip_dict(payload["issue"], _ISSUE_KEEP)
            return _strip_dict(payload, _ISSUE_KEEP | {"ok", "action", "card", "issue"})
        items = payload.get("items")
        if isinstance(items, list):
            payload["items"] = [
                _strip_dict(item, _ISSUE_KEEP) if isinstance(item, dict) else item for item in items
            ]
            return payload
        return _strip_dict(payload, _ISSUE_KEEP | {"ok", "action", "card"})

    if tool_name == "list_risk_events":
        items = payload.get("items")
        if isinstance(items, list):
            payload["items"] = [
                _strip_dict(item, _RISK_KEEP) if isinstance(item, dict) else item for item in items
            ]
        return payload

    # Generic: drop secrets only.
    return _strip_dict(payload, None)
