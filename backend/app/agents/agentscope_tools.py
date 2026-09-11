"""Wrap ManagementToolExecutor as AgentScope ToolBase instances.

AgentScope permission checks always ALLOW. Business RBAC, idempotency and
audit stay inside ManagementToolExecutor.
"""

from __future__ import annotations

from typing import Any

from app.agents.management_tools import WRITE_TOOLS, ManagementToolExecutor
from app.llm.schemas import ToolDefinition

try:
    from agentscope.message import TextBlock
    from agentscope.permission import (
        PermissionBehavior,
        PermissionContext,
        PermissionDecision,
    )
    from agentscope.tool import ToolBase, ToolChunk, Toolkit
except ImportError:  # pragma: no cover - optional until the image is rebuilt
    TextBlock = Any  # type: ignore[misc,assignment]
    PermissionBehavior = Any  # type: ignore[misc,assignment]
    PermissionContext = Any  # type: ignore[misc,assignment]
    PermissionDecision = Any  # type: ignore[misc,assignment]
    ToolBase = object  # type: ignore[misc,assignment]
    ToolChunk = Any  # type: ignore[misc,assignment]
    Toolkit = Any  # type: ignore[misc,assignment]


class ExecutorBoundTool(ToolBase):
    """One management tool bound to the current request's executor."""

    name = "pending"
    description = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    is_concurrency_safe = False
    is_read_only = True

    def __init__(
        self,
        definition: ToolDefinition,
        executor: ManagementToolExecutor,
        *,
        write_tools: frozenset[str] = WRITE_TOOLS,
    ) -> None:
        self.name = definition.name
        self.description = definition.description
        self.input_schema = definition.parameters or {
            "type": "object",
            "properties": {},
        }
        self.is_read_only = definition.name not in write_tools
        self._executor = executor
        super().__init__()

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Project tools are authorized by the signed-in user's RBAC.",
        )

    async def call(self, **kwargs: Any) -> ToolChunk:
        arguments = {
            key: value
            for key, value in kwargs.items()
            if key not in {"_agent_state", "tool_call_id"}
        }
        tool_call_id = kwargs.get("tool_call_id")
        envelope = self._executor.execute_result(
            self.name,
            arguments,
            tool_call_id=str(tool_call_id) if tool_call_id else None,
        )
        return ToolChunk(content=[TextBlock(text=envelope.to_json())])


def build_management_toolkit(executor: ManagementToolExecutor) -> Toolkit:
    """Register every MANAGEMENT_TOOLS entry against ``executor``."""
    from app.agents.management_tools import MANAGEMENT_TOOLS

    tools = [
        ExecutorBoundTool(definition, executor, write_tools=WRITE_TOOLS)
        for definition in MANAGEMENT_TOOLS
    ]
    return Toolkit(tools=tools)
