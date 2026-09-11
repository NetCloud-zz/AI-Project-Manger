"""Management Agent tool definitions and RBAC-aware executor."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.agents.tool_result import (
    ToolErrorCode,
    ToolResult,
    coerce_tool_result,
    public_error_message,
)
from app.llm.schemas import ToolDefinition
from app.models.user import User
from app.schemas.task import TaskPlanningFields
from app.services.agent_entities import EntityResolutionError, guard_mutation, resolve_arguments
from app.services.exceptions import (
    ActionItemNotFoundError,
    DomainValidationError,
    IssueNotFoundError,
    OwnerNotFoundError,
    PermissionDeniedError,
    ProjectCodeExistsError,
    ProjectNotFoundError,
    TaskNotFoundError,
    VersionConflictError,
)
from app.services.management_planning import ManagementPlanningService
from app.services.management_query import ManagementQueryService
from app.services.management_write import ManagementWriteService
from app.services.schedule_guard import ScheduleImpactRequiresProposal

_PROJECT_CODE_RE = re.compile(r"\b([A-Za-z]+-\d+)\b")

_OWNER_PROPS = {
    "owner_id": {
        "type": ["integer", "null"],
        "description": "User id of the owner/assignee; null leaves the task unassigned",
    },
    "owner_username": {
        "type": "string",
        "description": "Login username of the owner/assignee",
    },
    "owner_name": {
        "type": "string",
        "description": (
            "Display name of the owner/assignee (use find_users if ambiguous). "
            "Pass 待定/TBD/未指定 to leave unassigned."
        ),
    },
}

MANAGEMENT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_current_user",
        description=(
            "Return the authenticated actor (id / user_id, name, username, role) and business timezone. "
            "Use this for “我 / 我的任务”; never invent identity via find_users. "
            "Both id and user_id are the same numeric user primary key."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDefinition(
        name="list_projects",
        description="List all projects visible to the current user.",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDefinition(
        name="get_project",
        description="Get one project by id or project_code (e.g. PRJ-1001).",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Numeric project id"},
                "project_code": {
                    "type": "string",
                    "description": "Project code such as PRJ-1001",
                },
            },
        },
    ),
    ToolDefinition(
        name="search_tasks",
        description=(
            "Search tasks across visible projects with backend-resolved date presets. "
            "Use date_preset=today|tomorrow|this_week|next_week|next_7_days "
            "(this_week = Mon–Sun; next_7_days = today through today+6 inclusive). "
            "owner_scope=me means tasks owned by the current user (not merely visible). "
            "Do not use list_delayed_tasks to answer “今天/本周有什么任务”. "
            "For ad-hoc filters/aggregates prefer query_tasks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "owner_scope": {
                    "type": "string",
                    "enum": ["me", "user", "all"],
                    "description": "me=current user as owner; user=owner_id; all=any visible",
                },
                "owner_id": {
                    "type": "integer",
                    "description": "Required when owner_scope=user",
                },
                "date_preset": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "this_week", "next_week", "next_7_days"],
                },
                "due_from": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                "due_to": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
                },
                "keyword": {"type": "string"},
                "include_inactive": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "cursor": {"type": "integer", "description": "Continue after this task id"},
            },
        },
    ),
    ToolDefinition(
        name="query_tasks",
        description=(
            "Generic task Query DSL (filters/sort/group_by/aggregates) over permission-scoped "
            "tasks. Prefer this for overdue counts by project/owner. Never invent SQL. "
            "Whitelist fields only (task_name, status, due_date, is_overdue, progress_percent, …)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filters": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "group_by": {"type": "array", "items": {"type": "string"}},
                "aggregates": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
            },
        },
    ),
    ToolDefinition(
        name="search_projects",
        description="Query DSL over visible projects (filters/sort/limit).",
        parameters={
            "type": "object",
            "properties": {
                "filters": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
            },
        },
    ),
    ToolDefinition(
        name="search_issues",
        description="Query DSL over issues in visible projects.",
        parameters={
            "type": "object",
            "properties": {
                "filters": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
            },
        },
    ),
    ToolDefinition(
        name="list_my_tasks",
        description=(
            "Convenience wrapper of search_tasks with owner_scope=me — same as the "
            "“我的任务” page. Supports the same date_preset / status / project filters."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "date_preset": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "this_week", "next_week", "next_7_days"],
                },
                "due_from": {"type": "string"},
                "due_to": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
                },
                "keyword": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "cursor": {"type": "integer"},
            },
        },
    ),
    ToolDefinition(
        name="list_project_tasks",
        description="List tasks for a project, optionally filtered by owner name.",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "owner_name": {
                    "type": "string",
                    "description": "Partial match on task owner display name",
                },
            },
        },
    ),
    ToolDefinition(
        name="get_task_progress",
        description=(
            "Get task status, owner, due date, recent progress updates, and open issues. "
            "Use task_id for a single task, or project_code to summarize all tasks in a project."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "project_code": {"type": "string"},
            },
        },
    ),
    ToolDefinition(
        name="list_delayed_tasks",
        description="List delayed or overdue active tasks visible to the user.",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Optional project filter"},
            },
        },
    ),
    ToolDefinition(
        name="list_at_risk_tasks",
        description="List at-risk active tasks visible to the user.",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Optional project filter"},
            },
        },
    ),
    ToolDefinition(
        name="list_open_issues",
        description="List unresolved issues visible to the user.",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "task_id": {"type": "integer"},
            },
        },
    ),
    ToolDefinition(
        name="list_action_items",
        description=(
            "List action items (who does what by when). Defaults to unfinished items; "
            "set open_only=false to include DONE/CANCELLED."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "owner_name": {
                    "type": "string",
                    "description": "Partial match on action item owner display name",
                },
                "issue_id": {
                    "type": "integer",
                    "description": "Only action items following up on this issue",
                },
                "open_only": {"type": "boolean"},
            },
        },
    ),
    ToolDefinition(
        name="get_management_attention_items",
        description=(
            "List items that likely need management attention: critical issues, "
            "stale progress, delayed tasks, and delayed projects."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDefinition(
        name="find_users",
        description=(
            "Search one person by a partial name/username/email. For a list of exact "
            "display names prefer batch_find_users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Partial name, username, or email",
                },
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact display names; when set, runs one batch resolve",
                },
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
        },
    ),
    ToolDefinition(
        name="batch_find_users",
        description=(
            "Resolve many exact display names in one call. Returns resolved / ambiguous "
            "/ not_found. resolved is an array of {input, name, id, user_id, username, department}; "
            "id and user_id are the same. ambiguous contains {input, candidates}; not_found "
            "contains names. Prefer $ref like owners.<姓名>.user_id (or .id). Unresolved names "
            "are omitted from resolved, so its indices are not input indices. "
            "Do not call find_users once per person."
        ),
        parameters={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 200,
                }
            },
            "required": ["names"],
        },
    ),
    ToolDefinition(
        name="query_entities",
        description=(
            "Controlled Query DSL over a registered entity (task, project, issue, "
            "user, milestone, project_member). Whitelist fields/operators only. "
            "Never invent SQL or table names."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "enum": ["task", "project", "issue", "user", "milestone", "project_member"],
                },
                "filters": {"type": "array", "items": {"type": "object"}},
                "fields": {"type": "array", "items": {"type": "string"}},
                "order_by": {"type": "array", "items": {"type": "object"}},
                "sort": {"type": "array", "items": {"type": "object"}},
                "group_by": {"type": "array", "items": {"type": "string"}},
                "aggregates": {"type": "array", "items": {"type": "object"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["entity"],
        },
    ),
    ToolDefinition(
        name="batch_create_tasks",
        description=(
            "Create many tasks in one transaction. Validate all owners first; any "
            "invalid item rolls back the batch. Pass operation_id + client_item_id "
            "for idempotent retry of FAILED/PENDING items only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"},
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 500,
                    "items": {
                        "type": "object",
                        "properties": {
                            "client_item_id": {"type": "string"},
                            "task_name": {"type": "string"},
                            "owner_name": {"type": "string"},
                            "owner_id": {"type": "integer"},
                            "work_stream": {"type": "string"},
                            "start_date": {"type": "string"},
                            "due_date": {"type": "string"},
                        },
                        "required": ["client_item_id", "task_name"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
    ToolDefinition(
        name="batch_update_tasks",
        description=(
            "Update many tasks in one transaction. Retry only FAILED/PENDING items "
            "using the same operation_id and client_item_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 500,
                    "items": {
                        "type": "object",
                        "properties": {
                            "client_item_id": {"type": "string"},
                            "task_id": {"type": "integer"},
                            "task_name": {"type": "string"},
                            "owner_name": {"type": "string"},
                            "owner_id": {"type": "integer"},
                            "work_stream": {"type": "string"},
                        },
                        "required": ["client_item_id", "task_id"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
    ToolDefinition(
        name="create_project",
        description=(
            "Create a new project. Requires project_code, project_name, and an owner "
            "(owner_id / owner_username / owner_name). "
            "Optional: goal, start_date, target_date, owner_ids, status, risk_level."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_code": {
                    "type": "string",
                    "description": "Unique code, e.g. PRJ-2001",
                },
                "project_name": {"type": "string"},
                "goal": {"type": "string"},
                "target_date": {
                    "type": "string",
                    "description": "Project target date YYYY-MM-DD (initial set allowed)",
                },
                "status": {
                    "type": "string",
                    "enum": ["PLANNING", "ACTIVE", "COMPLETED", "CANCELLED"],
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["NORMAL", "AT_RISK", "DELAYED"],
                },
                "owner_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "description": (
                        "Complete owner set. All listed users are equal project owners; "
                        "order is not significant. On create, owner_id is included automatically."
                    ),
                },
                "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                **_OWNER_PROPS,
            },
            "required": ["project_code", "project_name"],
        },
    ),
    ToolDefinition(
        name="update_project",
        description=(
            "Edit an existing project by project_id or project_code. "
            "ADMIN or this project owner/co-owner may change dates with change_reason."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "change_reason": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 2000,
                    "description": "Required when changing project start_date or target_date",
                },
                "project_name": {"type": "string"},
                "goal": {"type": "string"},
                "target_date": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD; same edit permission as the REST endpoint",
                },
                "status": {
                    "type": "string",
                    "enum": ["PLANNING", "ACTIVE", "COMPLETED", "CANCELLED"],
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["NORMAL", "AT_RISK", "DELAYED"],
                },
                "owner_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 1,
                    "description": (
                        "Complete owner set. All listed users are equal project owners; "
                        "order is not significant. On create, owner_id is included automatically."
                    ),
                },
                "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                **_OWNER_PROPS,
            },
        },
    ),
    ToolDefinition(
        name="create_task",
        description=(
            "Create/assign a Level-3 execution task under a project. Requires task_name "
            "and project_id or project_code. Owner and start_date / due_date are optional "
            "(may be filled later; omit owner or pass a TBD label to leave unassigned). "
            "Use work_stream for the Level-2 phase name (e.g. 设计/开发) — phases themselves "
            "are not separate tasks and need no owner or dates."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "work_stream": {
                    "type": ["string", "null"],
                    "maxLength": 120,
                    "description": "Level-2 phase / work-stream name; no owner or dates needed on the phase itself",
                },
                "task_name": {"type": "string"},
                "due_date": {
                    "type": ["string", "null"],
                    "description": "Optional task due date YYYY-MM-DD",
                },
                "start_date": {
                    "type": ["string", "null"],
                    "description": "Optional start date YYYY-MM-DD",
                },
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
                },
                "progress_percent": {"type": "integer"},
                **_OWNER_PROPS,
            },
            "required": ["task_name"],
        },
    ),
    ToolDefinition(
        name="update_task",
        description=(
            "Edit a task: ADMIN or project owners/co-owners may edit core fields and dates. "
            "Task assignees may update status/progress only. Use branch tools to switch routes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "work_stream": {"type": ["string", "null"], "maxLength": 120},
                "task_name": {"type": "string"},
                "due_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD; same edit permission as the REST endpoint",
                },
                "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
                },
                "progress_percent": {"type": "integer"},
                "expected_version": {
                    "type": "integer",
                    "description": "Optimistic lock; from prior task.version",
                },
                "target_task_name": {"type": "string"},
                **_OWNER_PROPS,
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="assign_task",
        description=(
            "Domain action: change the owner of one execution task. "
            "Do not use for batch owner changes (propose_change)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "target_task_name": {"type": "string"},
                "project_code": {"type": "string"},
                "expected_version": {"type": "integer"},
                **_OWNER_PROPS,
            },
        },
    ),
    ToolDefinition(
        name="change_task_status",
        description="Domain action: change status of one execution task.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "target_task_name": {"type": "string"},
                "project_code": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"],
                },
                "expected_version": {"type": "integer"},
            },
            "required": ["status"],
        },
    ),
    ToolDefinition(
        name="reschedule_task",
        description=(
            "Domain action: change schedule of ONE execution task (due_date/start_date or "
            "offset_days). Do not use for work-stream or project-wide batch reschedules — "
            "those require propose_change."
        ),
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "target_task_name": {"type": "string"},
                "project_code": {"type": "string"},
                "due_date": {"type": "string"},
                "start_date": {"type": ["string", "null"]},
                "offset_days": {"type": "integer", "description": "Shift dates by N calendar days"},
                "shift_start": {"type": "boolean", "default": True},
                "expected_version": {"type": "integer"},
            },
        },
    ),
    ToolDefinition(
        name="create_issue",
        description=(
            "Log an unresolved problem for a project. Requires title and description plus "
            "project_id or project_code. Omit task_id for a project-level issue."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "task_id": {
                    "type": "integer",
                    "description": "Optional owning task; omit for project-level issues",
                },
                "title": {"type": "string"},
                "description": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
            },
            "required": ["title", "description"],
        },
    ),
    ToolDefinition(
        name="update_issue",
        description=(
            "Edit an existing issue by issue_id — change status, severity, title, "
            "or description. Set status=RESOLVED to close it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "issue_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "status": {
                    "type": "string",
                    "enum": ["OPEN", "IN_PROGRESS", "RESOLVED"],
                },
            },
            "required": ["issue_id"],
        },
    ),
    ToolDefinition(
        name="create_action_item",
        description=(
            "Create an action item (who does what by when) under a project. Requires title "
            "plus project_id or project_code. Optionally link a task or an issue, assign an "
            "owner, and set due_date/priority."
        ),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "task_id": {"type": "integer", "description": "Optional related task"},
                "issue_id": {"type": "integer", "description": "Optional related issue"},
                "due_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD (initial set allowed)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"],
                },
                "status": {
                    "type": "string",
                    "enum": ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"],
                },
                **_OWNER_PROPS,
            },
            "required": ["title"],
        },
    ),
    ToolDefinition(
        name="update_action_item",
        description=(
            "Edit an action item by action_item_id. Set status=DONE to close it. "
            "Dates follow item edit permission: admin, project owner/co-owner, assignee or author."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action_item_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "task_id": {"type": "integer"},
                "issue_id": {"type": "integer"},
                "due_date": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD; same edit permission as the REST endpoint",
                },
                "priority": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"],
                },
                "status": {
                    "type": "string",
                    "enum": ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"],
                },
                **_OWNER_PROPS,
            },
            "required": ["action_item_id"],
        },
    ),
]


# Keep the task planning input contract identical to REST/Pydantic.
for definition in MANAGEMENT_TOOLS:
    if definition.name in {"create_task", "update_task"}:
        definition.parameters["properties"].update(
            TaskPlanningFields.model_json_schema()["properties"]
        )


# Branch metadata is returned by task queries; mutations use the existing branch service.
MANAGEMENT_TOOLS.extend(
    [
        ToolDefinition(
            name="list_task_branches",
            description="List visible sibling routes for a task, including inactive history.",
            parameters={
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        ),
        ToolDefinition(
            name="create_task_branch",
            description=(
                "Create an alternative task route. ADMIN/project owners only; "
                "reason required. Defaults to inactive. activate=true also cancels "
                "unfinished sibling routes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "task_name": {"type": "string", "minLength": 1, "maxLength": 300},
                    "branch_label": {"type": "string", "minLength": 1, "maxLength": 80},
                    "owner_id": {"type": "integer"},
                    "start_date": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "work_stream": {"type": ["string", "null"], "maxLength": 120},
                    "activate": {"type": "boolean", "default": False},
                    "reason": {"type": "string", "minLength": 2, "maxLength": 2000},
                },
                "required": ["task_id", "task_name", "branch_label", "reason"],
            },
        ),
        ToolDefinition(
            name="activate_task_branch",
            description=(
                "Activate a route and cancel unfinished siblings, preserving completed "
                "records. Requires explicit user switch request and reason; "
                "ADMIN/project owners only."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "reason": {"type": "string", "minLength": 2, "maxLength": 2000},
                },
                "required": ["task_id", "reason"],
            },
        ),
    ]
)


# --- S4: planning context, drafting, change simulation, notifications --------
#
# The assistant may draft, simulate and propose. Publishing a plan, confirming a
# proposal and applying it are authorizations, so they only exist as REST
# endpoints the user hits from a card. There is deliberately no confirm tool.

_PROJECT_REF = {
    "project_id": {"type": "integer"},
    "project_code": {"type": "string", "description": "Project code such as PRJ-1001"},
}

_SCHEDULE_PATCH = {
    "type": "array",
    "maxItems": 200,
    "description": "Per-task schedule assumptions for the simulation",
    "items": {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer"},
            "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            "planned_duration_days": {"type": ["integer", "null"], "minimum": 1},
            "remaining_duration_days": {"type": ["integer", "null"], "minimum": 0},
            "earliest_start_date": {"type": ["string", "null"]},
            "fixed_start_date": {"type": ["string", "null"]},
            "fixed_due_date": {"type": ["string", "null"]},
        },
        "required": ["task_id"],
    },
}

_LINKS = {
    "type": "array",
    "maxItems": 2000,
    "description": "Complete dependency set for the candidate plan; omit to keep the current one",
    "items": {
        "type": "object",
        "properties": {
            "source_id": {"type": "integer"},
            "target_id": {"type": "integer"},
            "link_type": {
                "type": "string",
                "enum": [
                    "FINISH_TO_START",
                    "START_TO_START",
                    "FINISH_TO_FINISH",
                    "START_TO_FINISH",
                ],
            },
            "lag_days": {"type": "integer", "minimum": 0},
        },
        "required": ["source_id", "target_id"],
    },
}

_SELECTIONS = {
    "type": "array",
    "maxItems": 50,
    "description": "Route switches: which option each branch group should use",
    "items": {
        "type": "object",
        "properties": {
            "group_id": {"type": "integer"},
            "option_id": {"type": "integer"},
        },
        "required": ["group_id", "option_id"],
    },
}

_DRAFT_PLAN = {
    "type": "object",
    "description": "Complete draft plan. Send the full plan every time; it replaces the old one.",
    "properties": {
        "project": {
            "type": "object",
            "properties": {
                "project_code": {"type": "string", "description": "Unique code, e.g. PRJ-2001"},
                "project_name": {"type": "string"},
                "goal": {"type": "string"},
                "owner_id": {"type": "integer"},
                "owner_name": {"type": "string"},
                "owner_ids": {"type": "array", "items": {"type": "integer"}},
                "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "target_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            },
            "required": ["project_code", "project_name"],
        },
        "tasks": {
            "type": "array",
            "maxItems": 500,
            "items": {
                "type": "object",
                "properties": {
                    "client_id": {
                        "type": "integer",
                        "maximum": -1,
                        "description": "Negative temporary id used by links/milestones",
                    },
                    "task_name": {"type": "string"},
                    "owner_id": {"type": ["integer", "null"]},
                    "owner_name": {"type": ["string", "null"]},
                    "work_stream": {"type": ["string", "null"]},
                    "description": {"type": ["string", "null"]},
                    "deliverable": {"type": ["string", "null"]},
                    "acceptance_criteria": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "planned_duration_days": {"type": ["integer", "null"], "minimum": 1},
                    "earliest_start_date": {"type": ["string", "null"]},
                    "fixed_start_date": {"type": ["string", "null"]},
                    "fixed_due_date": {"type": ["string", "null"]},
                    "milestone_client_id": {"type": ["integer", "null"], "maximum": -1},
                    "estimate_basis": {
                        "type": ["string", "null"],
                        "description": "工期估算依据，例如 用户口述 / 模板 / AI 估算",
                    },
                },
                "required": ["client_id", "task_name"],
            },
        },
        "links": {
            "type": "array",
            "maxItems": 2000,
            "items": {
                "type": "object",
                "properties": {
                    "source_client_id": {"type": "integer", "maximum": -1},
                    "target_client_id": {"type": "integer", "maximum": -1},
                    "link_type": {
                        "type": "string",
                        "enum": [
                            "FINISH_TO_START",
                            "START_TO_START",
                            "FINISH_TO_FINISH",
                            "START_TO_FINISH",
                        ],
                    },
                    "lag_days": {"type": "integer", "minimum": 0},
                },
                "required": ["source_client_id", "target_client_id"],
            },
        },
        "milestones": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": {
                    "client_id": {"type": "integer", "maximum": -1},
                    "name": {"type": "string"},
                    "target_date": {"type": ["string", "null"]},
                    "deliverable": {"type": ["string", "null"]},
                    "acceptance_criteria": {"type": ["string", "null"]},
                },
                "required": ["client_id", "name"],
            },
        },
        "assumptions": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string"},
            "description": "Estimation assumptions the reviewer should be able to challenge",
        },
        "open_questions": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string"},
            "description": "Unanswered questions; a draft with these cannot be published",
        },
    },
    "required": ["project"],
}

MANAGEMENT_TOOLS.extend(
    [
        ToolDefinition(
            name="get_project_context",
            description=(
                "Structured facts for one project: tasks with planning fields, members, "
                "milestones, routes, dependencies, plan versions, open issues, recent "
                "progress and open change proposals. Permission filtered — read `access."
                "coverage` before claiming project-wide conclusions."
            ),
            parameters={"type": "object", "properties": dict(_PROJECT_REF)},
        ),
        ToolDefinition(
            name="get_dependency_graph",
            description=(
                "Effective tasks, four dependency types with lag, milestones and routes "
                "for one project. Project managers/executives only."
            ),
            parameters={"type": "object", "properties": dict(_PROJECT_REF)},
        ),
        ToolDefinition(
            name="draft_project_plan",
            description=(
                "Create a project plan draft from the conversation: project, tasks, "
                "dependencies, milestones, assumptions and open questions. Nothing is "
                "created in the real project — the user publishes from the draft card. "
                "Use find_users first to get real owner ids; never invent a person."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "plan": _DRAFT_PLAN,
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 100},
                },
                "required": ["plan"],
            },
        ),
        ToolDefinition(
            name="update_project_plan_draft",
            description=(
                "Replace the content of an existing draft after the user changes their "
                "mind. Always send the complete plan, not only the edited part."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string"},
                    "title": {"type": "string", "maxLength": 200},
                    "plan": _DRAFT_PLAN,
                    "expected_revision": {"type": "integer", "minimum": 1},
                },
                "required": ["draft_id", "plan"],
            },
        ),
        ToolDefinition(
            name="review_project_plan_draft",
            description=(
                "Check a draft for missing owners/dates, unknown people, duplicate "
                "project code, dependency cycles and unanswered questions. Returns the "
                "blocking list; only a draft with no blocking items can be published."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string"},
                    "expected_revision": {"type": "integer", "minimum": 1},
                },
                "required": ["draft_id"],
            },
        ),
        ToolDefinition(
            name="get_project_plan_draft",
            description="Read one plan draft by draft_id, or list the caller's drafts.",
            parameters={"type": "object", "properties": {"draft_id": {"type": "string"}}},
        ),
        ToolDefinition(
            name="validate_project_plan",
            description=(
                "Re-check a draft (owners, dates, duplicates, open questions) and return "
                "whether it is publishable. Does not create the real project."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string"},
                    "expected_revision": {"type": "integer", "minimum": 1},
                },
                "required": ["draft_id"],
            },
        ),
        ToolDefinition(
            name="apply_project_plan",
            description=(
                "Publish a reviewed draft in one transaction after the user explicitly "
                "confirms. Requires digest from validate/review. Never invent confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string"},
                    "digest": {"type": "string", "minLength": 64, "maxLength": 64},
                    "expected_revision": {"type": "integer", "minimum": 1},
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 100},
                },
                "required": ["draft_id", "digest"],
            },
        ),
        ToolDefinition(
            name="preview_change",
            description=(
                "Read-only schedule simulation: what happens to dependent tasks and the "
                "forecast finish date if durations, dates, dependencies, routes or the "
                "project target change. Writes nothing and sends nothing. Use this "
                "before proposing, and never state dates the engine did not return."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_PROJECT_REF,
                    "changes": _SCHEDULE_PATCH,
                    "links": _LINKS,
                    "selections": _SELECTIONS,
                    "project_target_date": {"type": ["string", "null"]},
                },
            },
        ),
        ToolDefinition(
            name="propose_change",
            description=(
                "Create and validate a change proposal covering task edits, new tasks, "
                "dependencies, route switches and the project target in one reviewed "
                "batch. Requires a written reason. This does NOT change the plan: the "
                "user must confirm and execute it on the proposal card. Say the plan is "
                "updated only after they do."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_PROJECT_REF,
                    "reason": {"type": "string", "minLength": 2, "maxLength": 2000},
                    "changes": {
                        "type": "array",
                        "maxItems": 1000,
                        "description": "Edits to existing tasks; may also set task_name/owner_id",
                        "items": {
                            "type": "object",
                            "properties": {
                                **_SCHEDULE_PATCH["items"]["properties"],  # type: ignore[index]
                                "task_name": {"type": "string"},
                                "owner_id": {"type": "integer"},
                                "work_stream": {"type": ["string", "null"]},
                                "description": {"type": ["string", "null"]},
                                "deliverable": {"type": ["string", "null"]},
                                "acceptance_criteria": {"type": ["string", "null"]},
                            },
                            "required": ["task_id"],
                        },
                    },
                    "new_tasks": {
                        "type": "array",
                        "maxItems": 200,
                        "description": "Tasks added by this change, e.g. a repeat experiment",
                        "items": {
                            "type": "object",
                            "properties": {
                                "client_id": {"type": "integer", "maximum": -1},
                                "task": {
                                    "type": "object",
                                    "properties": {
                                        "task_name": {"type": "string"},
                                        "owner_id": {"type": ["integer", "null"]},
                                        "due_date": {"type": ["string", "null"]},
                                        "start_date": {"type": ["string", "null"]},
                                        "work_stream": {"type": ["string", "null"]},
                                        "description": {"type": ["string", "null"]},
                                        "deliverable": {"type": ["string", "null"]},
                                        "planned_duration_days": {
                                            "type": ["integer", "null"],
                                            "minimum": 1,
                                        },
                                    },
                                    "required": ["task_name"],
                                },
                            },
                            "required": ["client_id", "task"],
                        },
                    },
                    "links": _LINKS,
                    "selections": _SELECTIONS,
                    "project_target_date": {"type": ["string", "null"]},
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 100},
                },
                "required": ["reason"],
            },
        ),
        ToolDefinition(
            name="get_change_proposal",
            description=(
                "Read one change proposal's status and difference summary, or list the "
                "project's proposals. Use this to answer 'did it go through?' — only "
                "status APPLIED means the plan actually changed."
            ),
            parameters={
                "type": "object",
                "properties": {**_PROJECT_REF, "proposal_id": {"type": "string"}},
            },
        ),
        ToolDefinition(
            name="execute_change_plan",
            description=(
                "Apply a change proposal that the CURRENT user has already CONFIRMED on "
                "the proposal card. Never confirm on the user's behalf. Requires "
                "proposal_id, digest, expected_revision and idempotency_key from "
                "get_change_proposal. If status is not CONFIRMED, ask the user to confirm "
                "in the UI first."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_PROJECT_REF,
                    "proposal_id": {"type": "string"},
                    "digest": {"type": "string", "minLength": 64, "maxLength": 64},
                    "expected_revision": {"type": "integer", "minimum": 1},
                    "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 100},
                },
                "required": ["proposal_id", "digest", "expected_revision", "idempotency_key"],
            },
        ),
        ToolDefinition(
            name="get_notification_status",
            description=(
                "Delivery state of plan-change notifications: by proposal_id for a "
                "proposal's recipients, or without it for the caller's own notices. "
                "SENT means the channel accepted the message, not that anyone read it; "
                "only ACKNOWLEDGED means the person confirmed in this system."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["QUEUED", "SENT", "FAILED", "ACKNOWLEDGED"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        ),
        ToolDefinition(
            name="submit_progress",
            description=(
                "Record a task progress report in the user's own words. Store what they "
                "said even when it is vague. A report is not permission to change the "
                "plan: if it implies a delay, follow up with preview_change/"
                "propose_change instead of editing dates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "content": {"type": "string", "minLength": 2, "maxLength": 5000},
                    "mark_completed": {"type": "boolean", "default": False},
                },
                "required": ["task_id", "content"],
            },
        ),
        ToolDefinition(
            name="list_risk_events",
            description=(
                "Tracked risk events (not project risk_level colours). "
                "Omit project_id/project_code to aggregate across all visible projects. "
                "OVERDUE is a fact; FORECAST_DELAY is a schedule prediction that never "
                "changes the committed target; MISSING_DATA means insufficient data — "
                "not that risk is absent. Do not answer risk questions from ON_TRACK alone."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_PROJECT_REF,
                    "status": {"type": "string", "enum": ["OPEN", "RESOLVED"]},
                    "event_type": {
                        "type": "string",
                        "enum": ["OVERDUE", "FORECAST_DELAY", "MISSING_DATA"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        ),
        ToolDefinition(
            name="get_issue_evidence",
            description=(
                "Selected, permission-filtered evidence for one problem: the linked task, "
                "its dependency neighbours, progress reports, other open issues, risks, "
                "action items and the baseline — each with a source id and update time. "
                "Also returns coverage and data_gaps. Cite source ids; state the gaps."
            ),
            parameters={
                "type": "object",
                "properties": {"issue_id": {"type": "integer"}},
                "required": ["issue_id"],
            },
        ),
        ToolDefinition(
            name="get_issue_advice",
            description=(
                "Advice versions recorded for one problem, with options, time impact, "
                "adoption status, linked action items and effectiveness. Read this before "
                "advising again so you do not repeat what was already rejected."
            ),
            parameters={
                "type": "object",
                "properties": {"issue_id": {"type": "integer"}},
                "required": ["issue_id"],
            },
        ),
        ToolDefinition(
            name="request_issue_advice",
            description=(
                "Queue a new evidence-based advice version for one problem. It produces a "
                "record for the user to accept or reject; it decides nothing and creates "
                "no action items by itself."
            ),
            parameters={
                "type": "object",
                "properties": {"issue_id": {"type": "integer"}},
                "required": ["issue_id"],
            },
        ),
    ]
)


MANAGEMENT_TOOLS.append(
    ToolDefinition(
        name="get_project_progress_overview",
        description=("查询项目最近进展、是否顺利：默认最近 7×24 小时汇报及当前延期/问题快照，"
                     "返回统计口径、事实覆盖和限制。"),
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
                "days": {"type": "integer", "minimum": 1, "maximum": 90},
            },
            "additionalProperties": False,
        },
    )
)
for _tool in MANAGEMENT_TOOLS:
    if _tool.name == "search_tasks":
        _tool.parameters.setdefault("properties", {}).update({"owner_name": {"type": "string"}, "statuses": {"type": "array", "items": {"type": "string", "enum": ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"]}}, "progress_min": {"type": "integer", "minimum": 0, "maximum": 100}, "progress_max": {"type": "integer", "minimum": 0, "maximum": 100}, "overdue": {"type": "boolean"}})
    if _tool.name in {"update_task", "get_task_progress", "submit_progress"}:
        _tool.parameters.setdefault("properties", {}).update(
            {
                "target_task_name": {
                    "type": "string",
                    "description": "精确任务名称；执行器在可见项目范围唯一匹配，重名返回候选项",
                },
                "project_id": {"type": "integer"},
                "project_code": {"type": "string"},
            }
        )
        _tool.parameters["required"] = [
            key for key in _tool.parameters.get("required", []) if key != "task_id"
        ]
    if _tool.name == "update_task":
        _tool.parameters["properties"]["new_task_name"] = {
            "type": "string",
            "description": "任务的新名称，区别于定位目标的 target_task_name",
        }

#: Tools handled by ManagementPlanningService, named identically to its methods.
_PLANNING_TOOLS = frozenset(
    {
        "get_project_context",
        "get_dependency_graph",
        "draft_project_plan",
        "update_project_plan_draft",
        "review_project_plan_draft",
        "get_project_plan_draft",
        "validate_project_plan",
        "apply_project_plan",
        "preview_change",
        "propose_change",
        "get_change_proposal",
        "execute_change_plan",
        "get_notification_status",
        "submit_progress",
        "list_risk_events",
        "get_issue_evidence",
        "get_issue_advice",
        "request_issue_advice",
    }
)

#: Tools that mutate business state (blocked on regenerate / read-only rounds).
WRITE_TOOLS = frozenset(
    {
        "create_project",
        "update_project",
        "create_task",
        "update_task",
        "assign_task",
        "change_task_status",
        "reschedule_task",
        "create_task_branch",
        "activate_task_branch",
        "create_issue",
        "update_issue",
        "create_action_item",
        "update_action_item",
        "batch_create_tasks",
        "batch_update_tasks",
        "draft_project_plan",
        "update_project_plan_draft",
        "apply_project_plan",
        "propose_change",
        "execute_change_plan",
        "submit_progress",
        "request_issue_advice",
    }
)


def _card_key(card: dict[str, Any]) -> tuple[Any, ...]:
    return (
        card.get("type"),
        card.get("proposal_id"),
        card.get("draft_id"),
        card.get("project_id"),
        card.get("recipient_id"),
        card.get("issue_id"),
    )


class ManagementToolExecutor:
    """Dispatch tool calls to query/write services with RBAC."""

    def __init__(
        self,
        db: Session,
        actor: User,
        *,
        allow_writes: bool = True,
        agent_request_id: int | None = None,
        auto_commit: bool = True,
        source_message: str | None = None,
    ) -> None:
        self._query = ManagementQueryService(db)
        self._write = ManagementWriteService(db, auto_commit=auto_commit)
        self._plan = ManagementPlanningService(db)
        self._actor = actor
        self._db = db
        self._allow_writes = allow_writes
        self._agent_request_id = agent_request_id
        self._write_sequence = 0
        self._source_message = source_message
        self.tools_used: list[str] = []
        #: Structured references the UI turns into actionable cards.
        self.cards: list[dict[str, Any]] = []
        #: Per-call envelopes for SSE / persistence (includes failures).
        self.execution_log: list[dict[str, Any]] = []

    def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        tool_call_id: str | None = None,
    ) -> str:
        envelope = self.execute_result(name, arguments, tool_call_id=tool_call_id)
        return envelope.to_json()

    def execute_result(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        tool_call_id: str | None = None,
    ) -> ToolResult:
        import time

        from app.agents.dto import sanitize_agent_data
        from app.agents.registry import ToolRiskLevel, get_tool_registry
        from app.models.agent_request import AgentOperationStatus
        from app.services.agent_idempotency import (
            get_operation,
            make_operation_id,
            record_operation,
        )

        args = arguments or {}
        self.tools_used.append(name)
        operation_id: str | None = None
        started = time.perf_counter()
        meta = get_tool_registry().require(name)

        if meta.risk_level == ToolRiskLevel.DESTRUCTIVE:
            envelope = ToolResult.failure(
                ToolErrorCode.DESTRUCTIVE_BLOCKED,
                "破坏性操作（硬删除等）不允许通过项目助手执行",
                tool_call_id=tool_call_id,
            )
            self.execution_log.append(envelope.storage_record(name=name))
            self._audit_tool_call(
                name=name,
                risk_level=meta.risk_level.value,
                tool_call_id=tool_call_id,
                arguments=args,
                envelope=envelope,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return envelope

        if name in WRITE_TOOLS and not self._allow_writes:
            envelope = ToolResult.failure(
                ToolErrorCode.WRITE_DISABLED,
                "重新生成默认只读重答，不重复执行写操作；如需再次写入请发送新的明确请求",
                tool_call_id=tool_call_id,
            )
            self.execution_log.append(envelope.storage_record(name=name))
            self._audit_tool_call(
                name=name,
                risk_level=meta.risk_level.value,
                tool_call_id=tool_call_id,
                arguments=args,
                envelope=envelope,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            return envelope

        if name in WRITE_TOOLS and self._agent_request_id is not None:
            self._write_sequence += 1
            operation_id = make_operation_id(
                request_id=self._agent_request_id,
                tool_name=name,
                arguments=args,
                tool_call_id=tool_call_id,
                sequence=self._write_sequence,
            )
            existing = get_operation(self._db, operation_id)
            if existing is not None and existing.result_json is not None:
                envelope = coerce_tool_result(
                    existing.result_json, tool_call_id=tool_call_id
                ).model_copy(update={"operation_id": operation_id})
                if envelope.ok and isinstance(envelope.data, dict):
                    card = envelope.data.get("card")
                    if isinstance(card, dict):
                        self._remember(card)
                self.execution_log.append(envelope.storage_record(name=name))
                self._audit_tool_call(
                    name=name,
                    risk_level=meta.risk_level.value,
                    tool_call_id=tool_call_id,
                    arguments=args,
                    envelope=envelope,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                return envelope

        try:
            # Do not session.rollback() on failure — that would wipe uncommitted
            # conversation rows sharing this Session (F16). Write tools commit
            # themselves; read failures are converted to ToolResult envelopes.
            result = self._dispatch(name, args)
            if isinstance(result, dict) and isinstance(result.get("card"), dict):
                self._remember(result["card"])
            lean = sanitize_agent_data(name, result)
            if isinstance(result, dict) and result.get("ok") is False:
                envelope = ToolResult.failure(
                    result.get("error_code") or ToolErrorCode.VALIDATION_FAILED,
                    str(result.get("message") or "批量操作未完成"),
                    tool_call_id=tool_call_id,
                    operation_id=operation_id or result.get("operation_id"),
                    data=lean,
                )
            else:
                envelope = ToolResult.success(
                    lean,
                    tool_call_id=tool_call_id,
                    operation_id=operation_id or (result.get("operation_id") if isinstance(result, dict) else None),
                )
        except EntityResolutionError as exc:
            envelope = ToolResult.failure(
                exc.code,
                exc.message,
                tool_call_id=tool_call_id,
                operation_id=operation_id,
                data={"candidates": exc.candidates},
            )
        except PermissionDeniedError as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.PERMISSION_DENIED,
                public_error_message(exc, fallback="没有权限执行该操作"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except ScheduleImpactRequiresProposal as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.REQUIRES_CHANGE_PROPOSAL,
                public_error_message(exc, fallback="该变更需要走变更方案确认"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
                data={
                    "impacted_tasks": exc.impacted,
                    "next_step": "改用 preview_change 与 propose_change，由用户在页面确认后执行",
                },
            )
        except (
            ProjectNotFoundError,
            TaskNotFoundError,
            IssueNotFoundError,
            ActionItemNotFoundError,
        ) as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.NOT_FOUND,
                public_error_message(exc, fallback="未找到相关对象"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except (DomainValidationError, OwnerNotFoundError, ProjectCodeExistsError) as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.INVALID_ARGUMENTS,
                public_error_message(exc, fallback="参数无效"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except VersionConflictError as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.VERSION_CONFLICT,
                public_error_message(exc, fallback="数据已被他人更新，请重新查询后再试"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
                data={"current": exc.current},
            )
        except ValueError as exc:
            message = str(exc)
            code = (
                ToolErrorCode.UNKNOWN_TOOL
                if message.startswith("Unknown tool:")
                else ToolErrorCode.INVALID_ARGUMENTS
            )
            envelope = ToolResult.failure(
                code,
                public_error_message(exc, fallback="参数无效"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except KeyError:
            envelope = ToolResult.failure(
                ToolErrorCode.INVALID_ARGUMENTS
                if name in {t.name for t in MANAGEMENT_TOOLS}
                else ToolErrorCode.UNKNOWN_TOOL,
                "工具缺少必要参数，请指定对象或明确名称"
                if name in {t.name for t in MANAGEMENT_TOOLS}
                else f"未知工具: {name}",
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except TimeoutError as exc:
            envelope = ToolResult.failure(
                ToolErrorCode.TIMEOUT,
                public_error_message(exc, fallback="工具执行超时"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )
        except Exception as exc:  # noqa: BLE001
            envelope = ToolResult.failure(
                ToolErrorCode.INTERNAL_ERROR,
                public_error_message(exc, fallback="工具执行失败"),
                tool_call_id=tool_call_id,
                operation_id=operation_id,
            )

        if name in WRITE_TOOLS and self._agent_request_id is not None and operation_id is not None:
            record_operation(
                self._db,
                request_id=self._agent_request_id,
                operation_id=operation_id,
                tool_name=name,
                arguments=args,
                status=(
                    AgentOperationStatus.SUCCEEDED if envelope.ok else AgentOperationStatus.FAILED
                ),
                result=envelope.model_dump(mode="json"),
                tool_call_id=tool_call_id,
            )

        self.execution_log.append(envelope.storage_record(name=name))
        self._audit_tool_call(
            name=name,
            risk_level=meta.risk_level.value,
            tool_call_id=tool_call_id,
            arguments=args,
            envelope=envelope,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return envelope

    def _audit_tool_call(
        self,
        *,
        name: str,
        risk_level: str,
        tool_call_id: str | None,
        arguments: dict[str, Any],
        envelope: ToolResult,
        duration_ms: int,
    ) -> None:
        from app.services.agent_tool_audit import record_tool_call

        try:
            record_tool_call(
                self._db,
                request_id=self._agent_request_id,
                conversation_id=None,
                user_id=self._actor.id,
                tool_name=name,
                risk_level=risk_level,
                tool_call_id=tool_call_id,
                arguments=arguments,
                result=envelope.model_dump(mode="json"),
                success=envelope.ok,
                error_code=envelope.error.code.value if envelope.error else None,
                duration_ms=duration_ms,
            )
        except Exception:  # noqa: BLE001 — audit must not break tool path
            pass

    def _remember(self, card: dict[str, Any]) -> None:
        """Keep the newest card per referenced object so the UI shows current state."""
        key = (
            card.get("type"),
            card.get("proposal_id"),
            card.get("draft_id"),
            card.get("project_id"),
            card.get("recipient_id"),
        )
        self.cards = [existing for existing in self.cards if _card_key(existing) != key]
        self.cards.append(card)

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        actor = self._actor
        if name in WRITE_TOOLS:
            guard_mutation(self._source_message, name, args)
        args = resolve_arguments(
            self._db, actor, name, args, source_message=self._source_message
        )
        if name == "get_project_progress_overview":
            return self._query.get_project_progress_overview(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
                days=int(args.get("days", 7)),
            )
        if name in _PLANNING_TOOLS:
            return getattr(self._plan, name)(actor, args)
        if name == "list_projects":
            return self._query.list_projects(actor)
        if name == "get_current_user":
            return self._query.get_current_user(actor)
        if name == "search_tasks":
            return self._query.search_tasks(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
                owner_scope=args.get("owner_scope") or "all",
                owner_id=args.get("owner_id"),
                date_preset=args.get("date_preset"),
                due_from=args.get("due_from"),
                due_to=args.get("due_to"),
                status=args.get("status"),
                keyword=args.get("keyword"),
                include_inactive=bool(args.get("include_inactive") or False),
                statuses=args.get("statuses"),
                progress_min=args.get("progress_min"),
                progress_max=args.get("progress_max"),
                overdue=args.get("overdue"),
                limit=int(args["limit"]) if args.get("limit") is not None else 50,
                cursor=args.get("cursor"),
            )
        if name == "query_tasks":
            return self._query.query_tasks(actor, args)
        if name == "search_projects":
            return self._query.search_projects(actor, args)
        if name == "search_issues":
            return self._query.search_issues(actor, args)
        if name == "list_my_tasks":
            return self._query.list_my_tasks(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
                date_preset=args.get("date_preset"),
                due_from=args.get("due_from"),
                due_to=args.get("due_to"),
                status=args.get("status"),
                keyword=args.get("keyword"),
                limit=int(args["limit"]) if args.get("limit") is not None else 50,
                cursor=args.get("cursor"),
            )
        if name == "get_project":
            return self._query.get_project(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
            )
        if name == "list_project_tasks":
            return self._query.list_project_tasks(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
                owner_name=args.get("owner_name"),
            )
        if name == "get_task_progress":
            return self._query.get_task_progress(
                actor,
                task_id=args.get("task_id"),
                project_code=args.get("project_code"),
            )
        if name == "list_delayed_tasks":
            return self._query.list_delayed_tasks(actor, project_id=args.get("project_id"))
        if name == "list_at_risk_tasks":
            return self._query.list_at_risk_tasks(actor, project_id=args.get("project_id"))
        if name == "list_open_issues":
            return self._query.list_open_issues(
                actor,
                project_id=args.get("project_id"),
                task_id=args.get("task_id"),
            )
        if name == "list_action_items":
            open_only = args.get("open_only")
            return self._query.list_action_items(
                actor,
                project_id=args.get("project_id"),
                project_code=args.get("project_code"),
                owner_name=args.get("owner_name"),
                issue_id=args.get("issue_id"),
                open_only=True if open_only is None else bool(open_only),
            )
        if name == "get_management_attention_items":
            return self._query.get_management_attention_items(actor)
        if name == "query_entities":
            return self._query.query_entities(actor, args)
        if name == "find_users":
            names = args.get("names")
            if names:
                return self._write.find_users(names=list(names))
            return self._write.find_users(
                query=args.get("query"),
                limit=int(args["limit"]) if args.get("limit") is not None else 20,
            )
        if name == "batch_find_users":
            return self._write.find_users(names=list(args.get("names") or []))
        if name == "batch_create_tasks":
            from app.services.agent_batch import AgentBatchService

            return AgentBatchService(self._db).batch_create_tasks(actor, args)
        if name == "batch_update_tasks":
            from app.services.agent_batch import AgentBatchService

            return AgentBatchService(self._db).batch_update_tasks(actor, args)
        if name == "create_project":
            return self._write.create_project(actor, args)
        if name == "update_project":
            return self._write.update_project(actor, args)
        if name == "create_task":
            return self._write.create_task(actor, args)
        if name == "update_task":
            return self._write.update_task(actor, args)
        if name == "assign_task":
            return self._write.assign_task(actor, args)
        if name == "change_task_status":
            return self._write.change_task_status(actor, args)
        if name == "reschedule_task":
            return self._write.reschedule_task(actor, args)
        if name == "list_task_branches":
            return self._query.list_task_branches(actor, int(args["task_id"]))
        if name == "create_task_branch":
            return self._write.create_task_branch(actor, args)
        if name == "activate_task_branch":
            return self._write.activate_task_branch(actor, args)
        if name == "create_issue":
            return self._write.create_issue(actor, args)
        if name == "update_issue":
            return self._write.update_issue(actor, args)
        if name == "create_action_item":
            return self._write.create_action_item(actor, args)
        if name == "update_action_item":
            return self._write.update_action_item(actor, args)
        msg = f"Unknown tool: {name}"
        raise ValueError(msg)


def extract_project_code(message: str) -> str | None:
    match = _PROJECT_CODE_RE.search(message)
    return match.group(1).upper() if match else None


def infer_stub_tools(message: str) -> list[tuple[str, dict[str, Any]]]:
    """Keyword-based tool selection when LLM is unavailable.

    Write intents are not executed in stub mode — they need structured fields
    from the LLM. Stub stays read-only.
    """
    text = message.lower()
    code = extract_project_code(message)
    if code and (
        "怎么样" in message
        or "状态" in message
        or "进展" in message
        or "顺利" in message
        or "关注" in message
    ):
        return [("get_project_progress_overview", {"project_code": code})]
    if code:
        return [("get_project", {"project_code": code})]
    if any(
        keyword in message
        for keyword in ("我的任务", "我负责", "我今天", "今天该做", "我有哪些任务", "我有什么任务")
    ):
        preset = None
        if "今天" in message:
            preset = "today"
        elif "本周" in message:
            preset = "this_week"
        elif "下周" in message:
            preset = "next_week"
        args: dict[str, Any] = {}
        if preset:
            args["date_preset"] = preset
        return [("list_my_tasks", args)]
    if any(keyword in message for keyword in ("今天", "本周", "下周", "未来7天", "未来七天")):
        if "下周" in message:
            preset = "next_week"
        elif "本周" in message:
            preset = "this_week"
        elif "未来7" in message or "未来七" in message:
            preset = "next_7_days"
        else:
            preset = "today"
        return [("search_tasks", {"date_preset": preset})]
    if any(keyword in text for keyword in ("延期任务", "哪些任务延期", "延期了", "逾期")):
        return [("list_delayed_tasks", {})]
    if any(
        keyword in message
        for keyword in ("风险记录", "有哪些风险", "项目风险", "所有风险", "全局风险")
    ):
        return [("list_risk_events", {})]
    if any(keyword in text for keyword in ("可能延期", "有风险", "at risk", "风险任务")):
        return [("list_at_risk_tasks", {})]
    if any(keyword in text for keyword in ("行动项", "action item", "待办", "跟进事项")):
        return [("list_action_items", {})]
    if any(keyword in text for keyword in ("问题", "issue", "未解决", "还没解决")):
        return [("list_open_issues", {})]
    if any(keyword in text for keyword in ("需要我处理", "需要处理", "关注", "attention")):
        return [("get_management_attention_items", {})]
    if any(keyword in text for keyword in ("项目", "project")):
        return [("list_projects", {})]
    return [("get_management_attention_items", {})]


def _extract_owner_name(message: str) -> str | None:
    match = re.search(r"([\u4e00-\u9fffA-Za-z]{2,10})当前负责", message)
    if match:
        return match.group(1)
    match = re.search(r"([\u4e00-\u9fffA-Za-z]{2,10})负责哪些", message)
    if match:
        return match.group(1)
    return None


def format_stub_reply(message: str, tool_results: list[tuple[str, Any]]) -> str:
    """Build a deterministic reply from tool outputs without LLM synthesis."""
    if not tool_results:
        return "没有查到相关数据。当前 LLM 未配置，我只能基于工具结果回答。"

    sections: list[str] = []
    for tool_name, payload in tool_results:
        if tool_name == "get_project":
            if isinstance(payload, dict) and not payload.get("found", True):
                sections.append("没有查到该项目。")
            elif isinstance(payload, dict):
                sections.append(
                    f"项目 {payload.get('project_code')}（{payload.get('project_name')}）"
                    f" 状态 {payload.get('status')}，风险 {payload.get('risk_level')}，"
                    f"负责人 {payload.get('owner_name')}，目标日期 {payload.get('target_date')}。"
                )
        elif tool_name == "get_task_progress":
            if isinstance(payload, dict) and not payload.get("found", True):
                sections.append("没有查到该项目或任务。")
            elif isinstance(payload, dict) and "tasks" in payload:
                project = payload.get("project", {})
                tasks = payload.get("tasks") or []
                if not tasks:
                    sections.append(f"项目 {project.get('project_code')} 下没有查到任务。")
                for task in tasks:
                    sections.append(_format_task_progress(task))
            elif isinstance(payload, dict) and isinstance(payload.get("task"), dict):
                sections.append(_format_task_progress(payload["task"]))
            elif isinstance(payload, dict):
                sections.append(_format_task_progress(payload))
        elif tool_name == "get_project_progress_overview":
            if isinstance(payload, dict) and not payload.get("found", True):
                code = payload.get("project_code") or ""
                sections.append(f"没有查到该项目进展概览{f'（{code}）' if code else ''}。")
            elif isinstance(payload, dict):
                window = payload.get("window") or {}
                counts = payload.get("counts") or {}
                coverage = payload.get("coverage") or {}
                project = payload.get("project") or {}
                sections.append(
                    f"项目 {project.get('project_code') or payload.get('project_code')} "
                    f"最近 {window.get('days', 7)} 天进展："
                    f"活跃任务 {counts.get('active_visible_tasks', '—')}，"
                    f"逾期未完成 {counts.get('overdue_unfinished', '—')}，"
                    f"开放问题 {counts.get('open_issues', '—')}，"
                    f"近期汇报 {counts.get('recent_updates', '—')}。"
                    f"未覆盖：无近期汇报任务 {coverage.get('tasks_without_recent_updates', '—')}；"
                    f"依赖评估={coverage.get('dependencies_evaluated')}。"
                    f"评估：{payload.get('assessment', '')}"
                )
        elif tool_name in (
            "list_delayed_tasks",
            "list_at_risk_tasks",
            "list_project_tasks",
            "search_tasks",
            "list_my_tasks",
        ):
            items = payload
            meta = ""
            if isinstance(payload, dict):
                items = payload.get("items") or []
                applied = payload.get("applied_filters") or {}
                date_range = applied.get("date_range") or {}
                if date_range:
                    meta = (
                        f"（业务时区 {payload.get('business_timezone')}，"
                        f"区间 {date_range.get('start_date')}—{date_range.get('end_date')}，"
                        f"命中 {payload.get('total', len(items))}）\n"
                    )
                if payload.get("coverage", {}).get("truncated"):
                    meta += "结果已截断，不能称为全部。\n"
            if not items:
                sections.append(f"{tool_name}：当前可见范围未查到任务。{meta}")
            else:
                lines = [
                    f"- {item.get('project_code')} / {item.get('task_name')} "
                    f"负责人 {item.get('owner_name')} "
                    f"计划截止 {item.get('planned_due_date') or item.get('due_date') or '未定'} "
                    f"状态 {item.get('status')} AI {item.get('ai_status')}"
                    for item in items
                    if isinstance(item, dict)
                ]
                sections.append(meta + ("\n".join(lines) if lines else "没有查到数据。"))
        elif tool_name == "get_current_user":
            if isinstance(payload, dict):
                sections.append(
                    f"当前用户 {payload.get('name')}（{payload.get('username')}），"
                    f"角色 {payload.get('role')}，时区 {payload.get('business_timezone')}。"
                )
        elif tool_name == "list_risk_events":
            if isinstance(payload, dict):
                events = payload.get("events") or []
                if not events:
                    sections.append("当前可见范围未查到风险记录。")
                else:
                    lines = [
                        f"- [{item.get('event_type')}] {item.get('project_code')} "
                        f"{item.get('title')} 首次 {item.get('first_seen_at')}"
                        for item in events
                        if isinstance(item, dict)
                    ]
                    note = payload.get("note") or ""
                    sections.append("\n".join(lines) + (f"\n{note}" if note else ""))
        elif tool_name == "list_open_issues":
            if not payload:
                sections.append("没有查到未解决的问题。")
            else:
                lines = [
                    f"- [{item.get('severity')}] {item.get('project_code')} "
                    f"{item.get('task_name')}: {item.get('title')}"
                    for item in payload
                    if isinstance(item, dict)
                ]
                sections.append("\n".join(lines))
        elif tool_name == "list_action_items":
            if not payload:
                sections.append("没有查到未完成的行动项。")
            else:
                lines = [
                    f"- [{item.get('priority')}] {item.get('project_code')} "
                    f"{item.get('title')} 负责人 {item.get('owner_name') or '未指派'} "
                    f"截止 {item.get('due_date') or '未设置'} 状态 {item.get('status')}"
                    for item in payload
                    if isinstance(item, dict)
                ]
                sections.append("\n".join(lines))
        elif tool_name == "get_management_attention_items":
            if not payload:
                sections.append("目前没有需要您特别处理的事项。")
            else:
                lines = [
                    f"- {item.get('project_code')}: {item.get('summary')}"
                    for item in payload
                    if isinstance(item, dict)
                ]
                sections.append("需要关注的事项：\n" + "\n".join(lines))
        elif tool_name == "list_projects":
            if not payload:
                sections.append("没有查到项目。")
            else:
                lines = [
                    f"- {item.get('project_code')} {item.get('project_name')} "
                    f"({item.get('risk_level')})"
                    for item in payload
                    if isinstance(item, dict)
                ]
                sections.append("\n".join(lines))

    body = "\n\n".join(section for section in sections if section)
    prefix = "（LLM 未配置，以下为工具查询结果）\n\n" if body else ""
    return prefix + (body or "没有查到相关数据。")


def _format_task_progress(task: dict[str, Any]) -> str:
    issues = task.get("open_issues") or []
    issue_text = (
        "；未解决问题：" + "、".join(issue.get("title", "") for issue in issues) if issues else ""
    )
    progress = task.get("recent_progress") or []
    latest = progress[0]["summary"] if progress and progress[0].get("summary") else None
    progress_text = f"最新进展：{latest}。" if latest else ""
    return (
        f"任务 {task.get('task_name')}（{task.get('project_code')}）"
        f" 负责人 {task.get('owner_name') or '待定'}，截止 {task.get('due_date') or '未定'}，"
        f"状态 {task.get('status')}，AI 状态 {task.get('ai_status')}。"
        f"{progress_text}{issue_text}"
    )
