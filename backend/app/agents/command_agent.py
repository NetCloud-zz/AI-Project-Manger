"""Model proposes a complete plan; the deterministic executor owns effects."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.management_tools import MANAGEMENT_TOOLS
from app.agents.stream_events import AgentStreamEvent
from app.core.config import Settings
from app.llm.gateway import LLMGateway
from app.llm.schemas import ChatMessage, ToolDefinition
from app.models.user import User
from app.schemas.agent_command import CommandPlanInput
from app.services.agent_commands import CommandService, format_execution
from app.services.exceptions import DomainValidationError

PLAN_TOOL = ToolDefinition(
    name="plan_commands",
    description="提交完整执行清单；此调用不直接修改业务数据。",
    parameters=CommandPlanInput.model_json_schema(),
)


async def command_stream(db: Session, gateway: LLMGateway, settings: Settings, message: str, actor: User, request_id: int, context_messages: list[ChatMessage] | None = None) -> AsyncIterator[AgentStreamEvent]:
    service = CommandService(db)
    rules = """先规划全部指令，只调用 plan_commands，禁止直接调用业务工具。
每项具有稳定 item_id、用户原文 source_text、arguments 和 depends_on；不得遗漏查询或写入。
expected_count 是实际工具步骤总数。原文明确创建 N 个任务时必须恰好 N 个 create_task。
任务名定位使用 target_task_name，可附 project_code/project_id；改名使用 new_task_name。
缺失实体 ID 时交给执行器用名称精确解析，不要编造 ID。
新建对象使用 {"$ref":"item_id.project.id"} 或 {"$ref":"item_id.task.id"} 引用结果，必须声明依赖。
有先后含义、同一对象的修改和修改后的查询都须声明依赖。独立任务不设依赖。
要么全部成功要么全部不做时 policy=atomic，否则 independent。
不明确的修改幅度不能补成数值。只读问题使用查询工具。
最近进展、顺利吗使用 get_project_progress_overview。
无法明确参数时仍列出该指令，由执行器返回具体错误；不得静默省略。
可用工具定义如下：\n"""
    messages = list(context_messages or [ChatMessage(role="user", content=message)])
    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=rules
            + json.dumps([t.model_dump() for t in MANAGEMENT_TOOLS], ensure_ascii=False),
        ),
    )
    for attempt in range(2):
        calls = []
        async for delta in gateway.chat_with_tools_stream(
            messages=messages, tools=[PLAN_TOOL], model=settings.LLM_MODEL_REASONING
        ):
            if delta.tool_calls:
                calls = list(delta.tool_calls)
        try:
            if len(calls) != 1 or calls[0].name != "plan_commands":
                raise ValueError("必须提交一个完整 plan_commands 清单")
            proposal = CommandPlanInput.model_validate(calls[0].arguments)
            plan = service.create(request_id, message, proposal)
        except (ValueError, ValidationError, DomainValidationError) as exc:
            if attempt == 0:
                messages.append(
                    ChatMessage(
                        role="user",
                        content=f"计划校验失败，尚未执行任何操作。请修正完整清单：{exc}",
                    )
                )
                continue
            rejected = service.reject(request_id, message, str(exc))
            yield AgentStreamEvent(event="card", data=service.snapshot(rejected))
            yield AgentStreamEvent(
                event="delta", data={"content": f"执行清单未通过校验，未执行任何操作：{exc}"}
            )
            return
        yield AgentStreamEvent(event="card", data=service.snapshot(plan))
        snapshot = await service.run(plan, actor)
        yield AgentStreamEvent(event="card", data=snapshot)
        yield AgentStreamEvent(event="delta", data={"content": format_execution(snapshot)})
        return
