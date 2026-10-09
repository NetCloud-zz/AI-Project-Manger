"""Core tools plus on-demand tool groups for the Project Assistant ReAct loop.

Every ``MANAGEMENT_TOOLS`` entry belongs either to the always-equipped core or
to exactly one named group. Groups are activated through ``reset_tools`` —
AgentScope's native meta tool, mirrored here for the legacy loop — whose result
carries the group's usage instructions. The executor itself still accepts every
registered tool; activation only shapes what the model sees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache

from app.agents.tool_result import ToolErrorCode, ToolResult
from app.llm.schemas import ChatMessage, ToolDefinition
from app.prompts import load_prompt

META_TOOL_NAME = "reset_tools"


@dataclass(frozen=True, slots=True)
class Toolset:
    name: str
    description: str
    tools: tuple[str, ...]

    @property
    def instructions(self) -> str:
        return load_prompt(f"toolsets/{self.name}")


TOOLSETS: tuple[Toolset, ...] = (
    Toolset(
        name="plan_draft",
        description="整份立项计划草案：起草、修改、审查、校验、查看与发布前检查。",
        tools=(
            "draft_project_plan",
            "update_project_plan_draft",
            "review_project_plan_draft",
            "get_project_plan_draft",
            "validate_project_plan",
            "apply_project_plan",
        ),
    ),
    Toolset(
        name="change_plan",
        description="排期影响预览、变更方案生成/查询/执行、依赖图、项目计划上下文、变更通知状态。",
        tools=(
            "preview_change",
            "propose_change",
            "get_change_proposal",
            "execute_change_plan",
            "get_dependency_graph",
            "get_project_context",
            "get_notification_status",
        ),
    ),
    Toolset(
        name="branches",
        description="任务备用路线（分支）的查询、创建与切换。",
        tools=("list_task_branches", "create_task_branch", "activate_task_branch"),
    ),
    Toolset(
        name="issue_advice",
        description="问题证据收集、问题建议的生成与历史版本查询。",
        tools=("get_issue_evidence", "get_issue_advice", "request_issue_advice"),
    ),
    Toolset(
        name="extra_queries",
        description=(
            "兼容查询工具 query_tasks / list_projects / list_project_tasks；常规查询无需激活。"
        ),
        tools=("query_tasks", "list_projects", "list_project_tasks"),
    ),
)

TOOLSETS_BY_NAME = {toolset.name: toolset for toolset in TOOLSETS}
GROUP_OF_TOOL = {tool: toolset.name for toolset in TOOLSETS for tool in toolset.tools}


def all_tools() -> list[ToolDefinition]:
    from app.agents.management_tools import MANAGEMENT_TOOLS

    return list(MANAGEMENT_TOOLS)


def core_tools() -> list[ToolDefinition]:
    return [tool for tool in all_tools() if tool.name not in GROUP_OF_TOOL]


def group_tools(name: str) -> list[ToolDefinition]:
    wanted = set(TOOLSETS_BY_NAME[name].tools)
    return [tool for tool in all_tools() if tool.name in wanted]


@cache
def meta_tool_definition() -> ToolDefinition:
    """Legacy-loop twin of AgentScope ``ResetTools``: booleans are the final state."""
    return ToolDefinition(
        name=META_TOOL_NAME,
        description=(
            "按当前任务装备专项工具组。参数是各工具组的最终状态：设为 true 的组被激活，"
            "未设为 true 的组会被关闭。返回已激活组的使用说明，必须遵守。"
        ),
        parameters={
            "type": "object",
            "properties": {
                toolset.name: {
                    "type": "boolean",
                    "default": False,
                    "description": toolset.description,
                }
                for toolset in TOOLSETS
            },
        },
    )


def full_toolset_prompt() -> str:
    """Appended to the system prompt when groups are disabled (every tool equipped)."""
    sections = [
        "当前已装备全部工具，无需调用 reset_tools。以下为各专项工具的使用说明：",
        *(toolset.instructions for toolset in TOOLSETS),
    ]
    return "\n\n".join(sections)


def with_toolset_prompt(messages: list[ChatMessage], *, enabled: bool) -> list[ChatMessage]:
    if enabled:
        return messages
    extra = full_toolset_prompt()
    updated = list(messages)
    for index, item in enumerate(updated):
        if item.role == "system":
            updated[index] = ChatMessage(role="system", content=f"{item.content}\n\n{extra}")
            return updated
    return [ChatMessage(role="system", content=extra), *updated]


class ToolsetState:
    """Which groups are active in the current legacy-loop turn."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.active: list[str] = []

    def tools(self) -> list[ToolDefinition]:
        if not self.enabled:
            return all_tools()
        visible = core_tools()
        for name in self.active:
            visible += group_tools(name)
        return [*visible, meta_tool_definition()]

    def reset(self, arguments: dict[str, object], *, tool_call_id: str | None) -> ToolResult:
        unknown = sorted(key for key in arguments if key not in TOOLSETS_BY_NAME)
        if unknown:
            return ToolResult.failure(
                ToolErrorCode.INVALID_ARGUMENTS,
                f"未知工具组：{', '.join(unknown)}。可用：{', '.join(TOOLSETS_BY_NAME)}",
                tool_call_id=tool_call_id,
            )
        self.active = [toolset.name for toolset in TOOLSETS if arguments.get(toolset.name) is True]
        return ToolResult.success(
            {
                "activated": list(self.active),
                "instructions": {name: TOOLSETS_BY_NAME[name].instructions for name in self.active},
            },
            tool_call_id=tool_call_id,
        )

    def inactive_error(self, tool: str, *, tool_call_id: str | None) -> ToolResult | None:
        if not self.enabled:
            return None
        group = GROUP_OF_TOOL.get(tool)
        if group is None or group in self.active:
            return None
        return ToolResult.failure(
            ToolErrorCode.TOOLSET_INACTIVE,
            f"工具 {tool} 属于工具组 {group}，请先调用 {META_TOOL_NAME}"
            f"（{json.dumps({group: True})}）后再试。",
            tool_call_id=tool_call_id,
        )


def tool_schema_chars(tools: list[ToolDefinition]) -> int:
    return len(json.dumps([tool.model_dump() for tool in tools], ensure_ascii=False))
