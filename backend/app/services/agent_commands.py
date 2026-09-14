"""Durable, bounded command execution. Database writes and receipts share a transaction."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import Connection, CursorResult, Engine
from sqlalchemy.orm import Session

from app.agents.management_tools import WRITE_TOOLS
from app.models.agent_command import AgentCommandItem, AgentCommandPlan
from app.models.agent_request import AgentRequest, AgentRequestStatus
from app.models.user import User
from app.schemas.agent_command import (
    CommandPlanInput,
    CommandRetryInput,
    requires_atomic,
    validate_coverage,
)
from app.services.exceptions import DomainValidationError

ATOMIC_TOOLS = frozenset(
    {
        "create_project",
        "update_project",
        "create_task",
        "update_task",
        "create_milestone",
        "create_issue",
        "update_issue",
        "create_action_item",
        "update_action_item",
    }
)
# These handlers are queries only. Each parallel call receives its own Session.
PARALLEL_READS = frozenset(
    {
        "get_project",
        "search_tasks",
        "list_project_tasks",
        "get_task_progress",
        "get_current_user",
        "list_projects",
        "get_project_progress_overview",
        "query_entities",
        "batch_find_users",
        "find_users",
    }
)

_RECOVERABLE_ITEM_STATES = frozenset({"FAILED", "BLOCKED", "PENDING", "ROLLED_BACK"})


def build_requirement_inventory(proposal: CommandPlanInput) -> list[dict[str, Any]]:
    """Stable business entries derived from write steps (not user-facing forms)."""
    requirements: list[dict[str, Any]] = []
    for item in proposal.items:
        tool = item.tool
        if tool in {"create_project", "update_project"}:
            requirements.append(
                {
                    "requirement_id": f"req_{item.item_id}",
                    "kind": "project",
                    "operation": "create" if tool.startswith("create") else "update",
                    "step_ids": [item.item_id],
                    "fields": {
                        key: item.arguments.get(key)
                        for key in (
                            "project_code",
                            "project_name",
                            "start_date",
                            "target_date",
                            "owner_name",
                        )
                        if item.arguments.get(key) is not None
                    },
                    "evidence_refs": [{"source": "message", "quote": item.source_text}],
                }
            )
            continue
        if tool == "create_milestone":
            requirements.append(
                {
                    "requirement_id": f"req_{item.item_id}",
                    "kind": "milestone",
                    "operation": "create",
                    "step_ids": [item.item_id],
                    "fields": {
                        key: item.arguments.get(key)
                        for key in (
                            "name",
                            "milestone_name",
                            "target_date",
                            "owner_name",
                            "deliverable",
                        )
                        if item.arguments.get(key) is not None
                    },
                    "evidence_refs": [{"source": "message", "quote": item.source_text}],
                }
            )
            continue
        if tool in {"create_task", "update_task"}:
            requirements.append(
                {
                    "requirement_id": f"req_{item.item_id}",
                    "kind": "task",
                    "operation": "create" if tool == "create_task" else "update",
                    "step_ids": [item.item_id],
                    "fields": {
                        key: item.arguments.get(key)
                        for key in (
                            "task_name",
                            "new_task_name",
                            "owner_name",
                            "owner_id",
                            "work_stream",
                            "start_date",
                            "due_date",
                            "planned_duration_days",
                        )
                        if item.arguments.get(key) is not None
                    },
                    "evidence_refs": [{"source": "message", "quote": item.source_text}],
                }
            )
            continue
        if tool == "batch_create_tasks":
            rows = item.arguments.get("items") or item.arguments.get("tasks") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                client_id = str(row.get("client_item_id") or "").strip() or "item"
                requirements.append(
                    {
                        "requirement_id": f"req_{item.item_id}_{client_id}",
                        "kind": "task",
                        "operation": "create",
                        "step_ids": [item.item_id],
                        "client_item_id": client_id,
                        "fields": {
                            key: row.get(key)
                            for key in (
                                "task_name",
                                "owner_name",
                                "owner_names",
                                "owners",
                                "owner_id",
                                "owner_ids",
                                "collaborator_names",
                                "work_stream",
                                "start_date",
                                "due_date",
                                "planned_duration_days",
                            )
                            if row.get(key) is not None
                        },
                        "evidence_refs": [{"source": "message", "quote": item.source_text}],
                    }
                )
            continue
        if tool in {"draft_project_plan", "apply_project_plan"}:
            requirements.append(
                {
                    "requirement_id": f"req_{item.item_id}",
                    "kind": "plan",
                    "operation": "draft" if tool.startswith("draft") else "apply",
                    "step_ids": [item.item_id],
                    "fields": {},
                    "evidence_refs": [{"source": "message", "quote": item.source_text}],
                }
            )
    return requirements


def _recovery_meta(
    *,
    status: str,
    unplanned: bool,
    needs_review: bool,
    items: list[AgentCommandItem],
    has_source: bool,
) -> dict[str, Any]:
    if unplanned:
        return {
            "recoverable": bool(has_source),
            "action": "restore_source" if has_source else None,
            "hint": (
                "原文已保留，可补充后重新发送生成新请求"
                if has_source
                else "清单未通过校验，且无可用原文"
            ),
            "item_ids": [],
        }
    if needs_review:
        return {
            "recoverable": True,
            "action": "review",
            "hint": "任务已写入，回读发现字段差异，请先核实业务对象，勿重复创建",
            "item_ids": [],
        }
    unknown_ids = [i.item_id for i in items if i.state == "UNKNOWN"]
    if unknown_ids:
        return {
            "recoverable": False,
            "action": "manual_verify",
            "hint": "存在中断未决项，请先核对业务对象后再决定是否恢复",
            "item_ids": unknown_ids,
        }
    retry_ids = [i.item_id for i in items if i.state in _RECOVERABLE_ITEM_STATES]
    if status in {"PARTIAL", "FAILED", "PAUSED", "READY"} and retry_ids:
        return {
            "recoverable": True,
            "action": "retry_pending",
            "hint": "可恢复未完成项；已成功步骤不会重复执行",
            "item_ids": retry_ids,
        }
    return {"recoverable": False, "action": None, "hint": None, "item_ids": []}


def _resolved_user_by_name(result: dict[str, Any], name: str) -> dict[str, Any]:
    """Resolve historical name-based refs only within an exact batch-user result.

    Never choose a candidate from ambiguous results or fall back to list order.
    This also lets failed, persisted plans resume without repeating successful reads.
    """
    if not all(isinstance(result.get(key), list) for key in ("resolved", "ambiguous", "not_found")):
        raise KeyError(name)
    if name in result["not_found"]:
        raise KeyError(f"{name}（未匹配到用户）")
    if any(isinstance(row, dict) and row.get("input") == name for row in result["ambiguous"]):
        raise KeyError(f"{name}（重名未选定）")
    matches = [
        row
        for row in result["resolved"]
        if isinstance(row, dict)
        and (row.get("input") == name or row.get("name") == name)
        and isinstance(row.get("user_id"), int)
    ]
    # Prefer exact input match when both appear.
    exact = [row for row in matches if row.get("input") == name]
    pool = exact or matches
    if len(pool) != 1:
        raise KeyError(name)
    return pool[0]


def resolve_refs(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            parts = str(value["$ref"]).split(".")
            result: Any = results[parts[0]]["data"]
            for part in parts[1:]:
                if isinstance(result, list):
                    result = result[int(part)]
                    continue
                if isinstance(result, dict):
                    if part in result:
                        result = result[part]
                    elif part == "id" and "user_id" in result:
                        result = result["user_id"]
                    elif part == "user_id" and "id" in result:
                        result = result["id"]
                    else:
                        result = _resolved_user_by_name(result, part)
                    continue
                result = result[part]
            return result
        return {k: resolve_refs(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_refs(v, results) for v in value]
    return value


class CommandService:
    def __init__(self, db: Session):
        self.db = db

    def start(self, request_id: int, source: str, actor: User) -> AgentCommandPlan:
        request = self.db.get(AgentRequest, request_id)
        if request is None or request.user_id != actor.id:
            raise DomainValidationError("执行请求不存在")
        existing = self.db.scalar(
            select(AgentCommandPlan).where(AgentCommandPlan.request_id == request_id)
        )
        if existing is not None:
            raise DomainValidationError("请求已有计划，请查看原清单；不会重复执行")
        plan = AgentCommandPlan(
            request_id=request_id,
            source=source,
            status="PLANNING",
            expected_count=0,
            planning_details={"attempts": []},
        )
        self.db.add(plan)
        self.db.commit()
        return plan

    def owned(self, request_id: int, actor: User) -> AgentCommandPlan:
        request = self.db.get(AgentRequest, request_id)
        if request is None or request.user_id != actor.id:
            raise DomainValidationError("执行请求不存在")
        plan = self.db.scalar(
            select(AgentCommandPlan).where(AgentCommandPlan.request_id == request_id)
        )
        if plan is None:
            raise DomainValidationError("该请求尚无执行计划")
        return plan

    def items(self, plan: AgentCommandPlan) -> list[AgentCommandItem]:
        return list(
            self.db.scalars(
                select(AgentCommandItem)
                .where(AgentCommandItem.plan_id == plan.id)
                .order_by(AgentCommandItem.ordinal)
            )
        )

    def create(
        self,
        request_id: int,
        source: str,
        proposal: CommandPlanInput,
        *,
        details: dict[str, Any] | None = None,
    ) -> AgentCommandPlan:
        from app.agents.management_tools import MANAGEMENT_TOOLS, WRITE_TOOLS

        spans = validate_coverage(proposal, source)
        # Product default: best-effort independent writes unless user asks all-or-nothing.
        policy = "atomic" if requires_atomic(source) else "independent"
        known = {t.name for t in MANAGEMENT_TOOLS}
        for item in proposal.items:
            if item.tool not in known:
                raise DomainValidationError(f"未知工具：{item.tool}")
            if policy == "atomic" and item.tool in WRITE_TOOLS and item.tool not in ATOMIC_TOOLS:
                raise DomainValidationError(
                    f"{item.tool} 需要专用业务流程，不支持普通原子批次，未执行任何操作"
                )
        plan = self.db.scalar(
            select(AgentCommandPlan).where(AgentCommandPlan.request_id == request_id)
        )
        if plan is not None and plan.status != "PLANNING":
            raise DomainValidationError("请求已有执行结果，不能覆盖原计划")
        plan = plan or AgentCommandPlan(
            request_id=request_id,
            source=source,
        )
        plan.policy, plan.expected_count, plan.status = policy, len(proposal.items), "READY"
        inventory = build_requirement_inventory(proposal)
        merged = dict(details or {})
        merged["requirements"] = inventory
        merged["phase"] = merged.get("phase") or "execute"
        plan.planning_details = merged
        self.db.add(plan)
        self.db.flush()
        for index, (item, span) in enumerate(zip(proposal.items, spans, strict=True)):
            self.db.add(
                AgentCommandItem(
                    plan_id=plan.id,
                    ordinal=index,
                    item_id=item.item_id,
                    tool=item.tool,
                    source_text=item.source_text,
                    source_start=span[0],
                    source_end=span[1],
                    arguments=item.arguments,
                    depends_on=item.depends_on,
                )
            )
        self.db.commit()
        return plan

    def snapshot(self, plan: AgentCommandPlan) -> dict[str, Any]:
        items = self.items(plan)
        counts = Counter(item.state for item in items)
        details = plan.planning_details or {}
        requirements = list(details.get("requirements") or [])
        status = plan.status
        if status == "READY" and items and all(item.state == "SUCCEEDED" for item in items):
            status = "COMPLETED"
        if status == "PLANNING":
            request = self.db.get(AgentRequest, plan.request_id)
            if request and request.status not in {
                AgentRequestStatus.ACCEPTED,
                AgentRequestStatus.RUNNING,
            }:
                status = "PLANNING_FAILED"
        unplanned = status in {"INVALID_PLAN", "NEEDS_INPUT", "PLANNING_FAILED"}
        created_task_count = 0
        created_milestone_count = 0
        needs_review = False
        for item in items:
            if item.state != "SUCCEEDED":
                continue
            payload = _tool_payload(item.result)
            if item.tool == "create_milestone":
                created_milestone_count += 1
                continue
            if item.tool == "create_task":
                created_task_count += 1
                continue
            if item.tool != "batch_create_tasks":
                continue
            if payload.get("needs_review") or (payload.get("verification") or {}).get(
                "status"
            ) == "NEEDS_REVIEW":
                needs_review = True
            if payload.get("created_task_count") is not None:
                created_task_count += int(payload["created_task_count"])
            else:
                verification = payload.get("verification") or {}
                ids = verification.get("created_task_ids") or []
                created_task_count += len(ids) if ids else int(verification.get("actual_count") or 0)
        error = (
            "清单尚未通过校验，未执行业务操作。请补充或重新整理指令。"
            if unplanned and not details
            else plan.error
        )
        if unplanned and error and "原文映射" in error:
            if "写入步骤必须能对上用户授权原文" in error:
                error = (
                    "执行清单里的任务原文未能对上授权内容（常见于确认上一轮创建时）。"
                    "原文已保留，请直接再次确认创建，或把完整任务清单一并重发。"
                )
            else:
                error = (
                    "人员或项目核对步骤的内部引用未对齐，任务尚未创建。"
                    "原文已保留，请重新发送或稍后再试，无需为了内部字段改写清单。"
                )
        recovery = details.get("recovery") or _recovery_meta(
            status=status,
            unplanned=unplanned,
            needs_review=needs_review,
            items=items,
            has_source=bool(plan.source),
        )
        return {
            "type": "execution_plan",
            "request_id": plan.request_id,
            "status": status,
            "policy": plan.policy,
            "revision": plan.revision,
            "expected_count": 0 if unplanned else plan.expected_count,
            "succeeded": counts["SUCCEEDED"],
            "business_succeeded": sum(
                1 for i in items if i.state == "SUCCEEDED" and i.tool in WRITE_TOOLS
            ),
            "created_task_count": created_task_count,
            "created_milestone_count": created_milestone_count,
            "needs_review": needs_review,
            "remaining": (
                0
                if unplanned
                else plan.expected_count - counts["SUCCEEDED"]
            ),
            "error": error,
            "source": plan.source if unplanned else None,
            "requirements": [] if unplanned else requirements,
            "business_item_count": 0 if unplanned else len(requirements),
            "planned_step_count": len(items),
            "unplanned": unplanned,
            "questions": details.get("questions", []),
            "planning_attempt_count": len(details.get("attempts", [])),
            "error_code": details.get("error_code"),
            "phase": details.get("phase"),
            "facts_count": len(details.get("facts") or []),
            "budget": details.get("budget"),
            "recovery": recovery,
            "items": [
                {
                    "item_id": i.item_id,
                    "tool": i.tool,
                    "source_text": i.source_text,
                    "source_start": i.source_start,
                    "source_end": i.source_end,
                    "arguments": i.arguments,
                    "depends_on": i.depends_on,
                    "state": i.state,
                    "attempts": i.attempts,
                    "result": i.result,
                }
                for i in items
            ],
        }

    def reconcile_after_interrupt(
        self, request_id: int, *, reason: str = "interrupted"
    ) -> AgentCommandPlan | None:
        """Finalize PLANNING/RUNNING plans after stop, disconnect, or stale reclaim.

        Already-committed write receipts stay; pending work becomes recoverable.
        RUNNING in-flight items become UNKNOWN and must be verified manually.
        """
        from app.agents.tool_result import ToolResult

        plan = self.db.scalar(
            select(AgentCommandPlan).where(AgentCommandPlan.request_id == request_id)
        )
        if plan is None:
            return None
        details = dict(plan.planning_details or {})
        details["interrupt_reason"] = reason
        if plan.status == "PLANNING":
            plan.status = "PLANNING_FAILED"
            plan.error = (plan.error or "整理已中断，未执行业务操作。")[:1000]
            details["error_code"] = details.get("error_code") or "COMMAND_INTERRUPTED"
            details["phase"] = "done"
            details["recovery"] = _recovery_meta(
                status="PLANNING_FAILED",
                unplanned=True,
                needs_review=False,
                items=[],
                has_source=bool(plan.source),
            )
            plan.planning_details = details
            self.db.commit()
            return plan
        if plan.status != "RUNNING":
            return plan
        rows = self.items(plan)
        for item in rows:
            if item.state == "RUNNING":
                item.state = "UNKNOWN"
                item.result = ToolResult.failure(
                    "RESULT_UNKNOWN",
                    "执行中断时该项可能已写入，请先核对业务对象，不能自动重试",
                ).model_dump(mode="json")
        states = [item.state for item in rows]
        if all(state == "SUCCEEDED" for state in states):
            plan.status = "COMPLETED"
        elif "PENDING" in states:
            plan.status = "PAUSED"
        elif "SUCCEEDED" in states:
            plan.status = "PARTIAL"
        else:
            plan.status = "FAILED"
        plan.revision += 1
        details["phase"] = "done"
        details["recovery"] = _recovery_meta(
            status=plan.status,
            unplanned=False,
            needs_review=False,
            items=rows,
            has_source=bool(plan.source),
        )
        plan.planning_details = details
        self.db.commit()
        return plan

    def reject(
        self,
        request_id: int,
        source: str,
        error: str,
        *,
        status: str = "INVALID_PLAN",
        details: dict[str, Any] | None = None,
    ) -> AgentCommandPlan:
        plan = self.db.scalar(
            select(AgentCommandPlan).where(AgentCommandPlan.request_id == request_id)
        )
        if plan is not None and plan.status != "PLANNING":
            raise DomainValidationError("不能覆盖已有执行清单")
        plan = plan or AgentCommandPlan(request_id=request_id, source=source)
        plan.status, plan.expected_count, plan.error = (
            status,
            0,
            error[:1000],
        )
        plan.planning_details = details
        self.db.add(plan)
        self.db.commit()
        return plan

    def retry(self, plan: AgentCommandPlan, command: CommandRetryInput) -> None:
        # Compare-and-swap prevents two browsers from scheduling the same retry.
        changed = self.db.execute(
            update(AgentCommandPlan)
            .where(
                AgentCommandPlan.id == plan.id,
                AgentCommandPlan.revision == command.expected_revision,
                AgentCommandPlan.status.in_(["PARTIAL", "FAILED", "PAUSED", "READY"]),
            )
            .values(status="READY", revision=AgentCommandPlan.revision + 1)
        )
        if cast(CursorResult, changed).rowcount != 1:
            self.db.rollback()
            raise DomainValidationError("计划已变化或正在执行，请刷新后重试")
        rows = self.items(plan)
        selected = set(command.item_ids)
        eligible = {
            i.item_id for i in rows if i.state in {"FAILED", "BLOCKED", "PENDING", "ROLLED_BACK"}
        }
        if not selected <= eligible:
            self.db.rollback()
            raise DomainValidationError("只能恢复未完成项；成功项不能重复执行")
        if plan.policy == "atomic" and selected != eligible:
            self.db.rollback()
            raise DomainValidationError("原子批次必须整体重试")
        for item in rows:
            if item.item_id in selected:
                item.state, item.result = "PENDING", None
        request = self.db.get(AgentRequest, plan.request_id)
        if request is not None:
            request.cancel_requested = False
        self.db.commit()

    async def run(
        self, plan: AgentCommandPlan, actor: User, *, budget: int = 100
    ) -> dict[str, Any]:
        try:
            return await self._run(plan, actor, budget=budget)
        except BaseException:
            # Do not leave RUNNING committed by the conversation error handler.
            # Worker receipts commit independently; pending work stays recoverable.
            self.db.rollback()
            raise

    async def _run(
        self, plan: AgentCommandPlan, actor: User, *, budget: int = 100
    ) -> dict[str, Any]:
        from app.agents.management_tools import WRITE_TOOLS, ManagementToolExecutor
        from app.agents.tool_result import ToolResult

        # Keep the plan row locked until execution finishes. A worker crash rolls
        # back RUNNING and every uncommitted effect; READY/PENDING remains resumable.
        changed = self.db.execute(
            update(AgentCommandPlan)
            .where(AgentCommandPlan.id == plan.id, AgentCommandPlan.status == "READY")
            .values(status="RUNNING")
        )
        if cast(CursorResult, changed).rowcount != 1:
            self.db.rollback()
            raise DomainValidationError("计划正在执行或需要先恢复")
        rows = self.items(plan)
        for item in rows:
            if item.state == "RUNNING":
                item.state = "UNKNOWN"
                item.result = ToolResult.failure(
                    "RESULT_UNKNOWN",
                    "上次专用流程执行中断，请核对业务对象后再决定下一步，不能自动重试",
                ).model_dump(mode="json")
        if plan.policy == "atomic" and sum(i.state == "PENDING" for i in rows) > budget:
            plan.status = "PAUSED"
            self.db.commit()
            return self.snapshot(plan)
        outer = self.db.begin_nested() if plan.policy == "atomic" else None
        failed = False
        steps = 0
        while steps < budget:
            request = self.db.scalar(
                select(AgentRequest)
                .where(AgentRequest.id == plan.request_id)
                .execution_options(populate_existing=True)
            )
            if request is not None and request.cancel_requested:
                failed = outer is not None
                details = dict(plan.planning_details or {})
                details["interrupt_reason"] = "cancel_requested"
                details["phase"] = "done"
                plan.planning_details = details
                break
            pending = [i for i in rows if i.state == "PENDING"]
            if not pending:
                break
            states = {i.item_id: i.state for i in rows}
            for _ in pending:
                propagated = False
                for item in pending:
                    if item.state == "PENDING" and any(
                        states[d] in {"FAILED", "BLOCKED", "ROLLED_BACK", "UNKNOWN"}
                        for d in item.depends_on
                    ):
                        item.state = states[item.item_id] = "BLOCKED"
                        item.result = ToolResult.failure(
                            "INVALID_STATE", "前置步骤未成功，未执行此项"
                        ).model_dump(mode="json")
                        propagated = True
                if not propagated:
                    break
            ready = [
                i
                for i in pending
                if i.state == "PENDING" and all(states[d] == "SUCCEEDED" for d in i.depends_on)
            ]
            if not ready:
                break
            resolved: dict[str, Any] = {}
            results = {i.item_id: i.result for i in rows if i.state == "SUCCEEDED"}
            invalid_reference = False
            for candidate in ready[: budget - steps]:
                try:
                    resolved[candidate.item_id] = resolve_refs(candidate.arguments, results)
                except (KeyError, IndexError, TypeError, ValueError):
                    candidate.state = "FAILED"
                    candidate.result = ToolResult.failure(
                        "INVALID_ARGUMENTS", "依赖结果缺少引用字段，未执行此项"
                    ).model_dump(mode="json")
                    candidate.attempts += 1
                    steps += 1
                    invalid_reference = True
            if invalid_reference:
                self.db.flush()
                if outer is not None:
                    failed = True
                    break
                continue
            item = ready[0]
            results = {i.item_id: i.result for i in rows if i.state == "SUCCEEDED"}
            batch: list[AgentCommandItem] = []
            for candidate in ready:
                if candidate.tool not in PARALLEL_READS or len(batch) >= min(4, budget - steps):
                    break
                batch.append(candidate)
            bind = self.db.get_bind()
            if item.tool in WRITE_TOOLS and outer is None and bind.dialect.name == "postgresql":
                # Only independent creates are parallel writes; updates may
                # touch the same aggregate and retain their source order.
                write_batch = [item]
                if item.tool == "create_task":
                    for candidate in ready[1:]:
                        if candidate.tool != "create_task" or len(write_batch) >= min(
                            4, budget - steps
                        ):
                            break
                        write_batch.append(candidate)
                await settled_workers(
                    *[
                        asyncio.to_thread(
                            _write,
                            bind,
                            actor.id,
                            plan.request_id,
                            i.id,
                            plan.source,
                            resolved[i.item_id],
                        )
                        for i in write_batch
                    ]
                )
                for candidate in write_batch:
                    self.db.refresh(candidate)
                steps += len(write_batch)
                continue
            # In-memory SQLite uses one physical connection and cannot isolate
            # worker sessions. Production PostgreSQL has independent connections.
            if (
                len(batch) > 1
                and bind.dialect.name != "sqlite"
                and outer is None
                and not any(i.state == "SUCCEEDED" and i.tool in ATOMIC_TOOLS for i in rows)
            ):
                self.db.flush()
                values = await settled_workers(
                    *[
                        asyncio.to_thread(_read, bind, actor.id, i.tool, resolved[i.item_id])
                        for i in batch
                    ]
                )
                for candidate, result in zip(batch, values, strict=True):
                    candidate.state = "SUCCEEDED" if result.ok else "FAILED"
                    candidate.result = result.model_dump(mode="json")
                    candidate.attempts += 1
                steps += len(batch)
                continue
            try:
                args = resolve_refs(item.arguments, results)
            except (KeyError, IndexError, TypeError, ValueError):
                result = ToolResult.failure("INVALID_ARGUMENTS", "依赖结果缺少引用字段，请修正计划")
            else:
                # Savepoint isolates validation failures, including flush errors.
                savepoint = self.db.begin_nested()
                executor = ManagementToolExecutor(
                    self.db, actor, auto_commit=False, source_message=plan.source
                )
                try:
                    result = (
                        ToolResult.failure(
                            "PLAN_REQUIRED", "该专用业务流程的可恢复执行需要 PostgreSQL"
                        )
                        if item.tool in WRITE_TOOLS and item.tool not in ATOMIC_TOOLS
                        else executor.execute_result(
                            item.tool, args, tool_call_id=f"plan-{plan.id}-{item.item_id}"
                        )
                    )
                    if result.ok:
                        savepoint.commit()
                    else:
                        savepoint.rollback()
                except Exception:
                    savepoint.rollback()
                    result = ToolResult.failure("INTERNAL_ERROR", "执行失败，当前项已回滚")
            item.attempts += 1
            item.result = result.model_dump(mode="json")
            item.state = "SUCCEEDED" if result.ok else "FAILED"
            steps += 1
            self.db.flush()
            if not result.ok:
                failed = True
                if outer is not None:
                    break
            # Commit receipts and effects together for independent primitives.
            # The request-wide lock stays held until all items finish; nested
            # savepoints give independent failure semantics without partial gaps.
        if outer is not None:
            if failed:
                receipts = {i.id: (i.state, i.result, i.attempts) for i in rows}
                outer.rollback()
                for item in rows:
                    state, result_data, attempts = receipts[item.id]
                    item.state = (
                        "ROLLED_BACK"
                        if state == "SUCCEEDED"
                        else ("BLOCKED" if state == "PENDING" else state)
                    )
                    item.result = (
                        result_data
                        if state != "SUCCEEDED"
                        else ToolResult.failure(
                            "INVALID_STATE", "原子批次失败，本项已回滚"
                        ).model_dump(mode="json")
                    )
                    item.attempts = attempts
            else:
                outer.commit()
        final_states = [i.state for i in rows]
        plan.status = (
            "COMPLETED"
            if all(s == "SUCCEEDED" for s in final_states)
            else (
                "PAUSED"
                if "PENDING" in final_states
                else ("PARTIAL" if "SUCCEEDED" in final_states else "FAILED")
            )
        )
        plan.revision += 1
        details = dict(plan.planning_details or {})
        details["phase"] = "verify" if any(
            (_tool_payload(i.result).get("needs_review") for i in rows if i.state == "SUCCEEDED")
        ) else "done"
        details["recovery"] = _recovery_meta(
            status=plan.status,
            unplanned=False,
            needs_review=details["phase"] == "verify",
            items=rows,
            has_source=bool(plan.source),
        )
        plan.planning_details = details
        self.db.commit()
        return self.snapshot(plan)


def _tool_payload(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if isinstance(data, dict):
        return data
    return result


def format_execution(snapshot: dict[str, Any]) -> str:
    from app.agents.stream_events import friendly_tool_name

    items = snapshot.get("items") or []
    business_ok = snapshot.get("business_succeeded")
    if business_ok is None:
        business_ok = sum(
            1
            for item in items
            if item.get("state") == "SUCCEEDED" and item.get("tool") in WRITE_TOOLS
        )
    created_tasks = snapshot.get("created_task_count")
    if created_tasks is None:
        created_tasks = 0
        for item in items:
            if item.get("state") != "SUCCEEDED" or item.get("tool") != "batch_create_tasks":
                continue
            payload = _tool_payload(item.get("result") if isinstance(item, dict) else None)
            if payload.get("created_task_count") is not None:
                created_tasks += int(payload["created_task_count"])
            else:
                verification = payload.get("verification") or {}
                ids = verification.get("created_task_ids") or []
                created_tasks += len(ids) if ids else int(verification.get("actual_count") or 0)
    if snapshot.get("unplanned"):
        error = (snapshot.get("error") or "").strip()
        if "原文映射" in error:
            if "写入步骤必须能对上用户授权原文" in error:
                return (
                    "执行清单里的任务原文未能对上授权内容（常见于确认上一轮创建时）。"
                    "原文已保留，请直接再次确认创建，或把完整任务清单一并重发。"
                )
            return (
                "人员或项目核对步骤的内部引用未对齐，任务尚未创建。"
                "系统会保留原文；请重新发送或稍后再试，无需为了内部字段改写清单。"
            )
        return error or "清单尚未通过校验，未执行业务操作。"
    review_note = "，回读发现字段差异待核实" if snapshot.get("needs_review") else ""
    lines = [
        f"指令执行：共 {snapshot['expected_count']} 个执行步骤，步骤成功 {snapshot['succeeded']}，"
        f"业务写入步骤成功 {business_ok}，实际创建任务 {created_tasks} 个"
        f"（状态 {snapshot['status']}{review_note}）。"
    ]
    for item in items:
        result = item.get("result") or {}
        error = result.get("error") or {}
        tool = str(item.get("tool") or "")
        label = friendly_tool_name(tool) if tool else item.get("item_id")
        lines.append(
            f"- {item['item_id']} · {label} · {item['source_text']}：{item['state']}"
            + (f"；{error.get('message', '')}" if error else "")
        )
    return "\n".join(lines)


async def settled_workers(*workers: Any) -> list[Any]:
    """A cancelled HTTP coroutine must not release the plan lock over live writes."""
    group = asyncio.gather(*workers, return_exceptions=True)
    try:
        outcomes = await asyncio.shield(group)
    except asyncio.CancelledError:
        await group
        raise
    if any(isinstance(outcome, BaseException) for outcome in outcomes):
        raise DomainValidationError("执行连接中断，请刷新清单核对已完成项，再恢复未执行项")
    return outcomes


def command_error_code(cards: list[dict[str, Any]] | None) -> str | None:
    """Transport completion is distinct from successful command execution."""
    for card in reversed(cards or []):
        if card.get("type") == "execution_plan":
            if card.get("status") != "COMPLETED":
                return str(
                    card.get("error_code") or "COMMAND_" + str(card.get("status", "INCOMPLETE"))
                )
            return None
    return None


def _read(bind: Engine | Connection, actor_id: int, tool: str, args: dict[str, Any]) -> Any:
    from app.agents.management_tools import ManagementToolExecutor
    from app.agents.tool_result import ToolResult

    try:
        with Session(bind=bind) as db:
            actor = db.get(User, actor_id)
            if actor is None:
                return ToolResult.failure("PERMISSION_DENIED", "用户不存在")
            return ManagementToolExecutor(db, actor, allow_writes=False).execute_result(tool, args)
    except Exception:
        return ToolResult.failure("INTERNAL_ERROR", "独立查询失败")


def _write(
    bind: Engine | Connection,
    actor_id: int,
    request_id: int,
    item_id: int,
    source: str,
    args: dict[str, Any],
) -> None:
    from app.agents.management_tools import ManagementToolExecutor
    from app.agents.tool_result import ToolResult

    with Session(bind=bind) as db:
        item = db.scalar(
            select(AgentCommandItem).where(AgentCommandItem.id == item_id).with_for_update()
        )
        if item is None:
            return
        if item.state != "PENDING":
            return
        actor = db.get(User, actor_id)
        if actor is None:
            return
        primitive = item.tool in ATOMIC_TOOLS
        if not primitive:
            item.state = "RUNNING"
            db.commit()
        savepoint = db.begin_nested() if primitive else None
        try:
            result = ManagementToolExecutor(
                db, actor, auto_commit=not primitive, source_message=source
            ).execute_result(item.tool, args, tool_call_id=f"command-{request_id}-{item.item_id}")
            if savepoint is not None:
                if result.ok:
                    savepoint.commit()
                else:
                    savepoint.rollback()
            interrupted = False
        except Exception:
            db.rollback()
            interrupted = True
            result = ToolResult.failure(
                "INTERNAL_ERROR" if primitive else "RESULT_UNKNOWN",
                "执行中断；数据库普通写入已回滚"
                if primitive
                else "专用流程结果未知，请先核对业务数据",
            )
        if result.ok:
            item.state = "SUCCEEDED"
        elif interrupted and not primitive:
            # Non-atomic tools may have committed before the exception; keep UNKNOWN.
            item.state = "UNKNOWN"
        else:
            item.state = "FAILED"
        item.result = result.model_dump(mode="json")
        item.attempts += 1
        db.commit()
