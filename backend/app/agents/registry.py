"""Management Agent tool registry — risk metadata without replacing tool schemas.

Phase 1: classify existing tools; Executor uses this for risk / audit / future gates.
LLM-facing schemas remain in ``MANAGEMENT_TOOLS`` (``ToolDefinition``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ToolRiskLevel(StrEnum):
    READ = "READ"
    LOW_WRITE = "LOW_WRITE"
    MEDIUM_WRITE = "MEDIUM_WRITE"
    HIGH_WRITE = "HIGH_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    name: str
    risk_level: ToolRiskLevel
    confirmation_required: bool = False
    plan_required: bool = False
    idempotency_required: bool = False
    deprecated: bool = False
    replacement: str | None = None
    description: str = ""


# Explicit overrides; anything else in WRITE_TOOLS defaults to LOW_WRITE,
# anything else defaults to READ.
_OVERRIDES: dict[str, RegisteredTool] = {
    "search_tasks": RegisteredTool(
        name="search_tasks",
        risk_level=ToolRiskLevel.READ,
        description="Primary task query; prefer over specialized list_* tools.",
    ),
    "list_my_tasks": RegisteredTool(
        name="list_my_tasks",
        risk_level=ToolRiskLevel.READ,
        deprecated=True,
        replacement="search_tasks",
        description="Deprecated wrapper; maps to search_tasks(owner_scope=me).",
    ),
    "submit_progress": RegisteredTool(
        name="submit_progress",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "create_issue": RegisteredTool(
        name="create_issue",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "create_action_item": RegisteredTool(
        name="create_action_item",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "create_task": RegisteredTool(
        name="create_task",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "create_project": RegisteredTool(
        name="create_project",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
        idempotency_required=True,
    ),
    "update_project": RegisteredTool(
        name="update_project",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
    ),
    "update_task": RegisteredTool(
        name="update_task",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
        description="Prefer specialized actions for owner/status/progress/schedule when available.",
    ),
    "create_task_branch": RegisteredTool(
        name="create_task_branch",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
    ),
    "activate_task_branch": RegisteredTool(
        name="activate_task_branch",
        risk_level=ToolRiskLevel.HIGH_WRITE,
        confirmation_required=True,
        plan_required=False,
    ),
    "reschedule_task": RegisteredTool(
        name="reschedule_task",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
        idempotency_required=True,
        description="Single-task schedule change; batch needs propose_change.",
    ),
    "assign_task": RegisteredTool(
        name="assign_task",
        risk_level=ToolRiskLevel.MEDIUM_WRITE,
        confirmation_required=True,
        idempotency_required=True,
    ),
    "change_task_status": RegisteredTool(
        name="change_task_status",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "query_tasks": RegisteredTool(
        name="query_tasks",
        risk_level=ToolRiskLevel.READ,
        description="Generic Query DSL for tasks.",
    ),
    "search_projects": RegisteredTool(
        name="search_projects",
        risk_level=ToolRiskLevel.READ,
    ),
    "search_issues": RegisteredTool(
        name="search_issues",
        risk_level=ToolRiskLevel.READ,
    ),
    "execute_change_plan": RegisteredTool(
        name="execute_change_plan",
        risk_level=ToolRiskLevel.HIGH_WRITE,
        confirmation_required=True,
        plan_required=True,
        idempotency_required=True,
        description="Apply only after user confirmed the proposal card.",
    ),
    "propose_change": RegisteredTool(
        name="propose_change",
        risk_level=ToolRiskLevel.HIGH_WRITE,
        confirmation_required=True,
        plan_required=True,
        idempotency_required=True,
    ),
    "preview_change": RegisteredTool(
        name="preview_change",
        risk_level=ToolRiskLevel.READ,
        description="Read-only schedule simulation; does not mutate plans.",
    ),
    "draft_project_plan": RegisteredTool(
        name="draft_project_plan",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
    "update_project_plan_draft": RegisteredTool(
        name="update_project_plan_draft",
        risk_level=ToolRiskLevel.LOW_WRITE,
    ),
    "request_issue_advice": RegisteredTool(
        name="request_issue_advice",
        risk_level=ToolRiskLevel.LOW_WRITE,
        idempotency_required=True,
    ),
}


class ToolRegistry:
    """Lookup risk metadata for tool names known to ManagementToolExecutor."""

    def __init__(self) -> None:
        self._by_name: dict[str, RegisteredTool] = dict(_OVERRIDES)

    def register(self, tool: RegisteredTool) -> None:
        self._by_name[tool.name] = tool

    def ensure_known(self, names: set[str], *, write_tools: set[str]) -> None:
        """Fill defaults for tools present in MANAGEMENT_TOOLS but not overridden."""
        for name in names:
            if name in self._by_name:
                continue
            if name in write_tools:
                self._by_name[name] = RegisteredTool(
                    name=name,
                    risk_level=ToolRiskLevel.LOW_WRITE,
                    idempotency_required=True,
                )
            else:
                self._by_name[name] = RegisteredTool(
                    name=name,
                    risk_level=ToolRiskLevel.READ,
                )

    def get(self, name: str) -> RegisteredTool | None:
        return self._by_name.get(name)

    def require(self, name: str) -> RegisteredTool:
        tool = self.get(name)
        if tool is None:
            return RegisteredTool(name=name, risk_level=ToolRiskLevel.READ)
        return tool

    def all_tools(self) -> list[RegisteredTool]:
        return list(self._by_name.values())


_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from app.agents.management_tools import MANAGEMENT_TOOLS, WRITE_TOOLS

        registry = ToolRegistry()
        registry.ensure_known(
            {item.name for item in MANAGEMENT_TOOLS},
            write_tools=set(WRITE_TOOLS),
        )
        _REGISTRY = registry
    return _REGISTRY


def reset_tool_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None
