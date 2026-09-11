"""Streaming event helpers for Project Assistant (PHASE C)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

StreamEventName = Literal[
    "message_start",
    "delta",
    "tool_start",
    "tool_end",
    "card",
    "done",
    "error",
]

TOOL_FRIENDLY_NAMES: dict[str, str] = {
    "list_projects": "查询项目列表",
    "get_project": "查询项目",
    "list_project_tasks": "查询任务",
    "get_task_progress": "查询任务进度",
    "list_delayed_tasks": "检查延期任务",
    "list_at_risk_tasks": "查询风险任务",
    "get_current_user": "确认当前用户",
    "search_tasks": "搜索任务",
    "list_my_tasks": "查询我的任务",
    "list_open_issues": "查询未解决问题",
    "list_action_items": "查询行动项",
    "get_management_attention_items": "查询管理关注事项",
    "find_users": "查询负责人",
    "batch_find_users": "批量查询负责人",
    "query_entities": "结构化查询",
    "batch_create_tasks": "批量创建任务",
    "batch_update_tasks": "批量更新任务",
    "validate_project_plan": "校验立项计划",
    "apply_project_plan": "发布立项计划",
    "create_project": "创建项目",
    "update_project": "更新项目",
    "create_task": "创建任务",
    "update_task": "更新任务",
    "list_task_branches": "查询任务分支",
    "create_task_branch": "创建备用分支",
    "activate_task_branch": "切换任务分支",
    "create_issue": "登记问题",
    "update_issue": "更新问题",
    "create_action_item": "创建行动项",
    "update_action_item": "更新行动项",
    "get_project_context": "读取项目上下文",
    "get_dependency_graph": "读取依赖与路线",
    "draft_project_plan": "起草立项计划",
    "update_project_plan_draft": "更新计划草案",
    "review_project_plan_draft": "校验计划草案",
    "get_project_plan_draft": "查看计划草案",
    "preview_change": "模拟变更影响",
    "propose_change": "生成变更方案",
    "get_change_proposal": "查看变更方案",
    "get_notification_status": "查询通知状态",
    "submit_progress": "提交进度汇报",
    "list_risk_events": "查询风险记录",
    "get_issue_evidence": "收集问题证据",
    "get_issue_advice": "查看问题建议",
    "request_issue_advice": "生成问题建议",
}


class AgentStreamEvent(BaseModel):
    event: StreamEventName
    data: dict[str, Any] = Field(default_factory=dict)


def friendly_tool_name(tool: str) -> str:
    return TOOL_FRIENDLY_NAMES.get(tool, tool)


def encode_sse(event: AgentStreamEvent | Mapping[str, Any]) -> bytes:
    name: str
    if isinstance(event, AgentStreamEvent):
        name = event.event
        payload = event.data
    else:
        name = str(event["event"])
        payload = dict(event.get("data") or {})
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {name}\ndata: {body}\n\n".encode()
