"""Whitelist of Agent Query DSL fields (logical names → Python attribute paths)."""

from __future__ import annotations

TASK_QUERY_FIELDS: dict[str, str] = {
    "task_id": "id",
    "id": "id",
    "task_code": "id",  # no separate code; id used for equality
    "task_name": "task_name",
    "title": "task_name",
    "project_id": "project_id",
    "project_code": "project.project_code",
    "work_stream": "work_stream",
    "status": "status",
    "progress": "progress_percent",
    "progress_percent": "progress_percent",
    "start_date": "start_date",
    "target_date": "due_date",
    "due_date": "due_date",
    "planned_due_date": "due_date",
    "risk_level": "ai_risk_level",
    "owner_id": "owner_id",
    "owner_name": "owner.name",
    "created_at": "created_at",
    # Computed (handled in policy/builder, not ORM getattr):
    "is_overdue": "__computed__",
    "days_overdue": "__computed__",
}

PROJECT_QUERY_FIELDS: dict[str, str] = {
    "project_id": "id",
    "id": "id",
    "project_code": "project_code",
    "project_name": "project_name",
    "status": "status",
    "risk_level": "risk_level",
    "owner_id": "owner_id",
    "start_date": "start_date",
    "target_date": "target_date",
}

ISSUE_QUERY_FIELDS: dict[str, str] = {
    "issue_id": "id",
    "id": "id",
    "project_id": "project_id",
    "task_id": "task_id",
    "title": "title",
    "status": "status",
    "severity": "severity",
}

USER_QUERY_FIELDS: dict[str, str] = {
    "id": "id",
    "name": "name",
    "username": "username",
    "department": "department",
    "role": "role",
    "status": "status",
}

MILESTONE_QUERY_FIELDS: dict[str, str] = {
    "id": "id",
    "project_id": "project_id",
    "name": "name",
    "target_date": "target_date",
    "status": "status",
    "owner_id": "owner_id",
}

PROJECT_MEMBER_QUERY_FIELDS: dict[str, str] = {
    "project_id": "project_id",
    "user_id": "user_id",
    "role": "role",
    "is_active": "is_active",
    "user_name": "user_name",
    "project_code": "project_code",
}

ENTITY_FIELDS = {
    "task": TASK_QUERY_FIELDS,
    "project": PROJECT_QUERY_FIELDS,
    "issue": ISSUE_QUERY_FIELDS,
    "user": USER_QUERY_FIELDS,
    "milestone": MILESTONE_QUERY_FIELDS,
    "project_member": PROJECT_MEMBER_QUERY_FIELDS,
}

QUERYABLE_ENTITIES = frozenset(ENTITY_FIELDS)
