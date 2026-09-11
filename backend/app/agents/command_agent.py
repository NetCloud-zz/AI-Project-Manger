"""Plan without side effects, preserve diagnostics, then execute validated steps."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.management_tools import MANAGEMENT_TOOLS
from app.agents.stream_events import AgentStreamEvent
from app.core.config import Settings
from app.core.security import SENSITIVE_FIELD_NAMES
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway
from app.llm.schemas import ChatMessage, ToolDefinition
from app.models.agent_request import AgentRequest
from app.models.user import User
from app.schemas.agent_command import CommandPlanInput, missing_source_fields, source_requirements
from app.services.agent_commands import CommandService, format_execution
from app.services.agent_entities import authorization_source
from app.services.exceptions import DomainValidationError

_parameters = CommandPlanInput.model_json_schema()
_parameters["properties"].pop("expected_count", None)
PLAN_TOOL = ToolDefinition(
    name="plan_commands",
    description="提交完整执行清单；总步骤数由系统计算。",
    parameters=_parameters,
)


def safe_candidate(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: safe_candidate(v) for k, v in value.items() if k.lower() not in SENSITIVE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [safe_candidate(v) for v in value]
    return value


def validation_feedback(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, ValidationError):
        return [
            {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
            for e in exc.errors(include_input=False, include_url=False, include_context=False)
        ]
    return [{"field": "plan", "message": str(exc)}]


async def command_stream(
    db: Session,
    gateway: LLMGateway,
    settings: Settings,
    message: str,
    actor: User,
    request_id: int,
    context_messages: list[ChatMessage] | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    service = CommandService(db)
    prior = [
        item.content
        for item in (context_messages or [])
        if item.role == "user" and isinstance(item.content, str) and item.content.strip()
    ]
    # Guard and coverage use the authorizing instruction (may be a prior create turn).
    auth_source = authorization_source(message, prior)
    plan = service.start(request_id, auth_source, actor)
    details: dict[str, Any] = {"requirements": source_requirements(auth_source), "attempts": []}
    questions = missing_source_fields(auth_source)
    if questions:
        details.update(questions=questions, error_code="COMMAND_INPUT_REQUIRED")
        plan = service.reject(
            request_id,
            auth_source,
            "需要补充信息，原始清单已保留，尚未创建业务对象。",
            status="NEEDS_INPUT",
            details=details,
        )
        yield AgentStreamEvent(event="card", data=service.snapshot(plan))
        yield AgentStreamEvent(
            event="delta",
            data={
                "content": "已保留原始清单，尚未创建项目或任务。请补充：\n"
                + "\n".join(f"- {q}" for q in questions)
                + "\n任务负责人与日期待定可先创建，后续再补齐；不会猜测负责人。可点击清单中的“补充／重新整理”。"
            },
        )
        return

    rules = """先规划全部指令，只调用 plan_commands，禁止直接执行业务工具。
每项具有唯一 item_id、用户原文 source_text、arguments 和 depends_on。
无需输出 expected_count，实际步骤数由系统计算；不能为凑数量增加或删除业务指令。
编号行一行对应至少一个独立执行项。source_text 必须完整引用该行内容，不要引用整篇原文。
阶段用 work_stream 等分组信息表示，里程碑与执行任务不能混淆，协作人员不能静默丢弃。
任务定位使用 target_task_name，可附 project_code/project_id；改名使用 new_task_name。
缺失 ID 用名称解析，不能编造。新对象使用 {"$ref":"item_id.project.id"} 或
{"$ref":"item_id.task.id"}；当前用户用 {"$ref":"cu.user_id"} 或 {"$ref":"cu.id"}
（get_current_user 同时提供 id 与 user_id），并在 depends_on 中声明。
batch_find_users 返回 {resolved:[{input,name,user_id}], ambiguous:[], not_found:[]}，
不是以姓名为键的字典。引用唯一匹配的负责人可用 {"$ref":"owners.人员姓名.user_id"}，
其中 owners 是查询步骤 item_id，人员姓名必须与请求姓名完全一致；执行器按唯一匹配解析，
不按请求顺序猜测 resolved 数组位置。查不到或有重名时不能选取其他人代替。
同一对象修改和修改后的查询需声明先后依赖；独立任务无依赖。
仅用户明确要求全部成功否则回滚时使用 atomic，否则 independent。
不猜测模糊修改的数值；日期未知可以留空；缺必要信息不能静默遗漏指令。
修正计划时保留所有未出错业务项，只修复反馈指出的问题，并提交完整清单。
可用工具：\n"""
    messages = list(context_messages or [ChatMessage(role="user", content=message)])
    messages.insert(
        0,
        ChatMessage(
            role="system",
            content=rules
            + json.dumps([t.model_dump() for t in MANAGEMENT_TOOLS], ensure_ascii=False),
        ),
    )
    public_error = (
        "执行清单仍有不完整或冲突的条目，尚未执行业务操作。原文和校验记录已保留，请补充或重新整理。"
    )
    failure_status = "INVALID_PLAN"
    for attempt in range(2):
        calls = []
        try:
            async with asyncio.timeout(settings.LLM_TIMEOUT_SECONDS):
                async for delta in gateway.chat_with_tools_stream(
                    messages=messages, tools=[PLAN_TOOL], model=settings.LLM_MODEL_REASONING
                ):
                    request = db.get(AgentRequest, request_id)
                    if request is not None:
                        db.refresh(request)
                    if request is not None and request.cancel_requested:
                        details["error_code"] = "COMMAND_STOPPED"
                        stopped = service.reject(
                            request_id,
                            auth_source,
                            "整理已停止，未执行业务操作。",
                            status="PLANNING_FAILED",
                            details=details,
                        )
                        yield AgentStreamEvent(event="card", data=service.snapshot(stopped))
                        return
                    if delta.tool_calls:
                        calls = list(delta.tool_calls)
        except (LLMError, TimeoutError) as exc:
            details["attempts"].append(
                {
                    "attempt": attempt + 1,
                    "error_type": type(exc).__name__,
                    "error_code": "COMMAND_MODEL_UNAVAILABLE",
                }
            )
            details["error_code"] = "COMMAND_MODEL_UNAVAILABLE"
            public_error = (
                "模型暂时未能完成清单整理，尚未执行业务操作。原文已保留，可稍后重新整理。"
            )
            failure_status = "PLANNING_FAILED"
            break

        candidate = safe_candidate(calls[0].arguments) if len(calls) == 1 else None
        record: dict[str, Any] = {
            "attempt": attempt + 1,
            "candidate": candidate,
            "declared_count": candidate.get("expected_count")
            if isinstance(candidate, dict)
            else None,
            "actual_count": len(candidate.get("items", []))
            if isinstance(candidate, dict) and isinstance(candidate.get("items"), list)
            else None,
        }
        details["attempts"].append(record)
        try:
            if len(calls) != 1 or calls[0].name != "plan_commands":
                raise ValueError("请提交一个完整 plan_commands 清单")
            proposal = CommandPlanInput.model_validate(calls[0].arguments)
            plan.planning_details = json.loads(json.dumps(details, ensure_ascii=False))
            db.commit()
            plan = service.create(request_id, auth_source, proposal, details=details)
        except (ValueError, DomainValidationError) as exc:
            record["errors"] = validation_feedback(exc)
            plan.planning_details = json.loads(json.dumps(details, ensure_ascii=False))
            db.commit()
            if attempt == 0:
                if len(calls) == 1:
                    messages.append(ChatMessage(role="assistant", content="", tool_calls=calls))
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=calls[0].id,
                            content=json.dumps(
                                {
                                    "ok": False,
                                    "errors": record["errors"],
                                    "declared_count": record["declared_count"],
                                    "actual_count": record["actual_count"],
                                    "requirements": details["requirements"],
                                },
                                ensure_ascii=False,
                            ),
                        )
                    )
                else:
                    messages.append(
                        ChatMessage(
                            role="user",
                            content="清单格式无效，请只调用一次 plan_commands 并提供完整 items。",
                        )
                    )
                continue
            details["error_code"] = "COMMAND_PLAN_INVALID"
            break
        yield AgentStreamEvent(event="card", data=service.snapshot(plan))
        snapshot = await service.run(plan, actor)
        yield AgentStreamEvent(event="card", data=snapshot)
        yield AgentStreamEvent(event="delta", data={"content": format_execution(snapshot)})
        return
    rejected = service.reject(
        request_id, auth_source, public_error, status=failure_status, details=details
    )
    yield AgentStreamEvent(event="card", data=service.snapshot(rejected))
    yield AgentStreamEvent(event="delta", data={"content": public_error})
