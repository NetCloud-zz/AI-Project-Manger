"""Database business tools derived from docs/database; no database credentials.

Copyright 2024–2026 Jack Zhang. Apache License 2.0; retain NOTICE attribution.
"""

from __future__ import annotations

from app.llm.schemas import ToolDefinition
from app.services.agent_change_policy import ALWAYS_REASON, REASON_FIELDS

DATABASE_TOOLS = [
    ToolDefinition(
        name="get_database_tools",
        description="读取本项目工具契约：业务实体、可调用工具、增查改边界和修改原因规则。",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolDefinition(
        name="get_task",
        description="按任务业务编号读取可见任务及全部负责人；业务编号不是数据库 ID。",
        parameters={
            "type": "object",
            "properties": {
                "task_code": {"type": "string", "minLength": 2, "maxLength": 64},
            },
            "required": ["task_code"],
            "additionalProperties": False,
        },
    ),
    ToolDefinition(
        name="get_plan_version",
        description="读取项目历史计划版本摘要（只读）；需要完整项目读取权限，不输出原始快照。",
        parameters={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "minimum": 1},
                "version": {"type": "integer", "minimum": 1},
            },
            "required": ["project_id", "version"],
            "additionalProperties": False,
        },
    ),
]


def apply_database_contract(definitions: list[ToolDefinition]) -> None:
    """Publish the same reason requirements that services enforce."""
    for tool in definitions:
        if tool.name == "batch_update_tasks":
            tool.parameters["properties"]["items"]["items"]["properties"]["change_reason"] = {
                "type": "string",
                "minLength": 2,
                "maxLength": 2000,
                "description": "修改 work_stream 时逐条提供用户给出的原因。",
            }
            tool.description += (
                " Only task_name, owner_id/owner_name, work_stream are supported;"
                " work_stream requires change_reason per item."
            )
        if tool.name not in REASON_FIELDS and tool.name not in ALWAYS_REASON:
            continue
        key = (
            "reason"
            if tool.name in {"create_task_branch", "activate_task_branch", "propose_change"}
            else "change_reason"
        )
        tool.parameters.setdefault("properties", {})[key] = {
            "type": "string",
            "minLength": 2,
            "maxLength": 2000,
            "description": "用户提供的修改原因；缺少时询问用户，禁止助手编造。",
        }
        if tool.name in ALWAYS_REASON:
            required = tool.parameters.setdefault("required", [])
            if key not in required:
                required.append(key)
        fields = ", ".join(sorted(REASON_FIELDS.get(tool.name, ())))
        tool.description += (
            f" 修改这些字段（含清空）必须提供 {key}: {fields}。"
            if fields
            else f" 必须提供用户给出的 {key}。"
        )


def database_tool_catalog() -> dict:
    from app.agents.management_tools import MANAGEMENT_TOOLS, WRITE_TOOLS
    from app.agents.query.fields import ENTITY_FIELDS

    return {
        "contract": "project-database-tools-v1",
        "operations": ["READ", "CREATE", "UPDATE"],
        "sql_allowed": False,
        "delete_allowed": False,
        "scope": "当前认证用户 RBAC + 对象级权限；先过滤，再分页和聚合",
        "entities": {entity: list(fields) for entity, fields in ENTITY_FIELDS.items()},
        "semantics": {
            "project_direction": "project.goal",
            "work_stream": "任务的文本工作流维度；不是独立表",
            "task_group": "结构化任务分组树",
            "branch": "任务备选分支、路线组和路线选项；切换需原因",
            "owner": "主负责人 + OWNER 参与者；COLLABORATOR 不等于负责人",
            "owner_projection": (
                "owner_id/owner_name 标量显示主负责人；owners/owner_ids 显示全部负责人。"
                "负责人过滤匹配全部 OWNER，标量排序/分组仍按主负责人。"
            ),
            "history": "历史计划版本不可修改；完整快照不经通用查询输出",
        },
        "reason_fields": {name: sorted(fields) for name, fields in REASON_FIELDS.items()},
        "always_requires_reason": sorted(ALWAYS_REASON),
        "confirmation": (
            "影响计划的变更使用 preview_change → propose_change → 用户确认卡片；"
            "保留发布权限和并发校验"
        ),
        "tools": [
            {"name": t.name, "operation": "WRITE" if t.name in WRITE_TOOLS else "READ"}
            for t in MANAGEMENT_TOOLS
        ],
    }


def export_database_tool_definitions() -> dict:
    """Export schemas for integrations without opening a database connection."""
    from app.agents.management_tools import MANAGEMENT_TOOLS

    return {
        **database_tool_catalog(),
        "definitions": [tool.model_dump(mode="json") for tool in MANAGEMENT_TOOLS],
    }
