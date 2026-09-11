"""Batch user resolve and transactional task writes for structured Agent intents."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.owner_labels import is_pending_owner_label
from app.core.permissions import can_create_task, can_modify_task_core
from app.models.agent_batch import AgentBatchItem, AgentBatchOperation
from app.models.task import Task
from app.models.user import User, UserStatus
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.management_write import ManagementWriteService, _optional_str, _parse_date
from app.services.project import ProjectService
from app.services.task import TaskService

_SUCCESS = "SUCCESS"
_FAILED = "FAILED"
_PENDING = "PENDING"
_SKIPPED = "SKIPPED"
_MAX_ITEMS = 500


def _real_owner_names(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in items:
        name = str(row.get("owner_name") or "").strip()
        if name and not is_pending_owner_label(name):
            names.append(name)
    return names


def _item_view(item: AgentBatchItem) -> dict[str, Any]:
    return {
        "client_item_id": item.client_item_id,
        "status": item.status,
        "resource_id": item.resource_id,
        "error_code": item.error_code,
        "error_message": item.error_message,
    }


class AgentBatchService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectService(db)
        self.tasks = TaskService(db)
        self.users = ManagementWriteService(db, auto_commit=False)

    def find_users_batch(self, names: list[str]) -> dict[str, Any]:
        return self.users.find_users(names=names)

    def batch_create_tasks(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        items = self._incoming_items(args)
        project = self._project(actor, args)
        if not can_create_task(actor, project, self.db):
            raise PermissionDeniedError("You cannot create tasks in this project")
        operation = self._operation(actor, args, "batch_create_tasks", expected=len(items))
        existing = self._items_by_client(operation.operation_id)
        names = _real_owner_names(items)
        people = self.users.find_users(names=names) if names else {"resolved": [], "ambiguous": [], "not_found": []}
        resolved = {row["input"]: row for row in people["resolved"]}
        ambiguous = {row["input"]: row for row in people["ambiguous"]}
        missing = set(people["not_found"])

        prepared: list[tuple[dict[str, Any], AgentBatchItem, TaskCreate | None]] = []
        invalid = False
        for raw in items:
            client_id = str(raw["client_item_id"])
            row = existing.get(client_id) or self._new_item(operation.operation_id, client_id, raw)
            existing[client_id] = row
            if row.status == _SUCCESS and row.resource_id:
                row.status = _SUCCESS
                prepared.append((raw, row, None))
                continue
            error = self._validate_create_item(project, raw, resolved, ambiguous, missing)
            if error:
                invalid = True
                row.status, row.error_code, row.error_message, row.resource_id = (
                    _FAILED,
                    error["error_code"],
                    error["message"],
                    None,
                )
                prepared.append((raw, row, None))
                continue
            owner_id: int | None = None
            if raw.get("owner_id") is not None:
                owner_id = int(raw["owner_id"])
            elif raw.get("owner_name"):
                name = str(raw["owner_name"]).strip()
                if name and not is_pending_owner_label(name):
                    owner_id = int(resolved[name]["user_id"])
            prepared.append(
                (
                    raw,
                    row,
                    TaskCreate(
                        task_name=str(raw["task_name"]).strip(),
                        owner_id=owner_id,
                        work_stream=_optional_str(raw, "work_stream"),
                        start_date=_parse_date(raw.get("start_date"), field="start_date"),
                        due_date=_parse_date(raw.get("due_date"), field="due_date"),
                    ),
                )
            )

        if invalid:
            operation.status = "VALIDATION_FAILED"
            self.db.commit()
            return self._failed_payload(operation, existing, "VALIDATION_FAILED", "批量创建未写入：存在无法解析的条目")

        created_ids: list[int] = []
        try:
            with self.db.begin_nested():
                for raw, row, payload in prepared:
                    if payload is None:
                        continue
                    task = self.tasks.create_task(project.id, payload, actor=actor)
                    self.db.flush()
                    row.status = _SUCCESS
                    row.resource_id = str(task.id)
                    row.error_code = None
                    row.error_message = None
                    created_ids.append(task.id)
                verification = self._verify_create(project.id, operation.operation_id, items, existing)
                if verification["status"] != _SUCCESS:
                    raise DomainValidationError("VALIDATION_FAILED")
        except Exception:
            for raw, row, payload in prepared:
                if payload is not None and row.status != _SUCCESS:
                    row.status = _FAILED
                    row.error_code = row.error_code or "INTERNAL_ERROR"
                    row.error_message = row.error_message or "批量写入已回滚"
            operation.status = "FAILED"
            self.db.commit()
            return self._failed_payload(operation, existing, "VALIDATION_FAILED", "批量创建已回滚，未留下部分任务")

        operation.status = _SUCCESS
        operation.details = {"created_ids": created_ids}
        self.db.commit()
        return {
            "ok": True,
            "action": "batch_create_tasks",
            "operation_id": operation.operation_id,
            "items": [_item_view(existing[str(row["client_item_id"])]) for row in items],
            "verification": self._verify_create(project.id, operation.operation_id, items, existing),
        }

    def batch_update_tasks(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        items = self._incoming_items(args)
        operation = self._operation(actor, args, "batch_update_tasks", expected=len(items))
        existing = self._items_by_client(operation.operation_id)
        names = _real_owner_names(items)
        people = self.users.find_users(names=names) if names else {"resolved": [], "ambiguous": [], "not_found": []}
        resolved = {row["input"]: row for row in people["resolved"]}
        invalid = False
        prepared: list[tuple[Task, TaskUpdate, AgentBatchItem]] = []
        for raw in items:
            client_id = str(raw["client_item_id"])
            row = existing.get(client_id) or self._new_item(operation.operation_id, client_id, raw)
            existing[client_id] = row
            if row.status == _SUCCESS:
                continue
            try:
                task = self.tasks.get_task(int(raw["task_id"]))
            except Exception:
                invalid = True
                row.status, row.error_code, row.error_message = _FAILED, "NOT_FOUND", "任务不存在"
                continue
            if not can_modify_task_core(actor, task, task.project, self.db):
                invalid = True
                row.status, row.error_code, row.error_message = (
                    _FAILED,
                    "PERMISSION_DENIED",
                    "没有权限修改该任务",
                )
                continue
            updates: dict[str, Any] = {}
            if raw.get("task_name"):
                updates["task_name"] = str(raw["task_name"]).strip()
            if raw.get("work_stream") is not None:
                updates["work_stream"] = _optional_str(raw, "work_stream")
            if "owner_id" in raw or "owner_name" in raw:
                owner_id = raw.get("owner_id")
                if owner_id is None:
                    name = str(raw.get("owner_name") or "").strip()
                    if not name or is_pending_owner_label(name):
                        updates["owner_id"] = None
                    elif name not in resolved:
                        invalid = True
                        row.status, row.error_code, row.error_message = (
                            _FAILED,
                            "OWNER_NOT_FOUND",
                            f"未找到唯一匹配用户: {name}",
                        )
                        continue
                    else:
                        updates["owner_id"] = int(resolved[name]["user_id"])
                else:
                    updates["owner_id"] = int(owner_id)
            prepared.append((task, TaskUpdate(**updates), row))

        if invalid:
            operation.status = "VALIDATION_FAILED"
            self.db.commit()
            return self._failed_payload(operation, existing, "VALIDATION_FAILED", "批量更新未写入：存在无效条目")

        try:
            with self.db.begin_nested():
                for task, payload, row in prepared:
                    updated = self.tasks.update_task(
                        task.id, payload, actor=actor, allow_core_fields=True
                    )
                    row.status = _SUCCESS
                    row.resource_id = str(updated.id)
                    row.error_code = None
                    row.error_message = None
        except Exception:
            operation.status = "FAILED"
            self.db.commit()
            return self._failed_payload(operation, existing, "VALIDATION_FAILED", "批量更新已回滚")

        operation.status = _SUCCESS
        self.db.commit()
        verified = {
            "status": _SUCCESS,
            "expected_count": len(items),
            "actual_count": sum(1 for item in existing.values() if item.status == _SUCCESS),
            "duplicate_count": 0,
            "missing_items": [],
            "unexpected_items": [],
        }
        return {
            "ok": True,
            "action": "batch_update_tasks",
            "operation_id": operation.operation_id,
            "items": [_item_view(existing[str(row["client_item_id"])]) for row in items],
            "verification": verified,
        }

    def _incoming_items(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        items = args.get("items") or []
        if not isinstance(items, list) or not items:
            raise DomainValidationError("items 不能为空")
        if len(items) > _MAX_ITEMS:
            raise DomainValidationError(f"单次最多 {_MAX_ITEMS} 条")
        seen: set[str] = set()
        normalized = []
        for raw in items:
            client_id = str((raw or {}).get("client_item_id") or "").strip()
            if not client_id:
                raise DomainValidationError("每条记录必须提供 client_item_id")
            if client_id in seen:
                raise DomainValidationError(f"client_item_id 重复：{client_id}")
            seen.add(client_id)
            normalized.append(dict(raw))
        return normalized

    def _project(self, actor: User, args: dict[str, Any]):
        project = None
        code = str(args.get("project_code") or "").strip()
        if code:
            project = self.projects.repo.get_by_code(code)
        if project is None and args.get("project_id") is not None:
            project = self.projects.repo.get_by_id(int(args["project_id"]))
        if project is None:
            raise DomainValidationError("未找到项目")
        return project

    def _operation(
        self, actor: User, args: dict[str, Any], tool_name: str, *, expected: int
    ) -> AgentBatchOperation:
        operation_id = str(args.get("operation_id") or f"op_{uuid.uuid4().hex[:16]}")
        row = self.db.scalar(
            select(AgentBatchOperation).where(AgentBatchOperation.operation_id == operation_id)
        )
        if row is None:
            row = AgentBatchOperation(
                operation_id=operation_id,
                user_id=actor.id,
                tool_name=tool_name,
                status=_PENDING,
                expected_count=expected,
            )
            self.db.add(row)
            self.db.flush()
        elif row.user_id != actor.id:
            raise PermissionDeniedError("不能复用他人的 operation_id")
        row.expected_count = expected
        return row

    def _items_by_client(self, operation_id: str) -> dict[str, AgentBatchItem]:
        rows = self.db.scalars(
            select(AgentBatchItem).where(AgentBatchItem.operation_id == operation_id)
        ).all()
        return {row.client_item_id: row for row in rows}

    def _new_item(self, operation_id: str, client_id: str, payload: dict[str, Any]) -> AgentBatchItem:
        row = AgentBatchItem(
            operation_id=operation_id,
            client_item_id=client_id,
            status=_PENDING,
            payload=payload,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _validate_create_item(
        self,
        project,
        raw: dict[str, Any],
        resolved: dict[str, Any],
        ambiguous: dict[str, Any],
        missing: set[str],
    ) -> dict[str, str] | None:
        name = str(raw.get("task_name") or "").strip()
        if not name:
            return {"error_code": "INVALID_ARGUMENTS", "message": "task_name 必填"}
        owner_name = str(raw.get("owner_name") or "").strip()
        if raw.get("owner_id") is None and owner_name and not is_pending_owner_label(owner_name):
            if owner_name in missing:
                return {
                    "error_code": "OWNER_NOT_FOUND",
                    "message": f"未找到唯一匹配用户: {owner_name}",
                }
            if owner_name in ambiguous:
                return {
                    "error_code": "AMBIGUOUS_ENTITY",
                    "message": f"负责人重名: {owner_name}",
                }
            if owner_name not in resolved:
                return {
                    "error_code": "OWNER_NOT_FOUND",
                    "message": f"未找到唯一匹配用户: {owner_name}",
                }
        exists = self.db.scalar(
            select(Task.id).where(Task.project_id == project.id, Task.task_name == name)
        )
        client_id = str(raw["client_item_id"])
        current = self.db.scalar(
            select(AgentBatchItem).where(
                AgentBatchItem.operation_id == raw.get("_operation_id", ""),
                AgentBatchItem.client_item_id == client_id,
                AgentBatchItem.status == _SUCCESS,
            )
        )
        if exists and current is None:
            # Same name already in project and not this item's previous success.
            owned = self.db.scalar(
                select(AgentBatchItem).where(
                    AgentBatchItem.resource_id == str(exists),
                    AgentBatchItem.status == _SUCCESS,
                )
            )
            if owned is None:
                return {
                    "error_code": "DUPLICATE_TASK",
                    "message": f"项目中已存在同名任务: {name}",
                }
        return None

    def _verify_create(
        self,
        project_id: int,
        operation_id: str,
        items: list[dict[str, Any]],
        existing: dict[str, AgentBatchItem],
    ) -> dict[str, Any]:
        expected_names = [str(row["task_name"]).strip() for row in items]
        rows = list(
            self.db.scalars(select(Task).where(Task.project_id == project_id, Task.task_name.in_(expected_names)))
        )
        by_name: dict[str, list[int]] = defaultdict(list)
        for task in rows:
            by_name[task.task_name].append(task.id)
        missing = [name for name in expected_names if name not in by_name]
        duplicates = [name for name, ids in by_name.items() if len(ids) > 1]
        resource_ids = {item.resource_id for item in existing.values() if item.resource_id}
        unexpected = [
            str(task.id)
            for task in rows
            if str(task.id) not in resource_ids and existing.get(next((k for k, v in existing.items() if v.resource_id == str(task.id)), ""), None) is None
        ]
        status = _SUCCESS if not missing and not duplicates else "VALIDATION_FAILED"
        return {
            "status": status,
            "expected_count": len(items),
            "actual_count": len(rows),
            "duplicate_count": sum(len(ids) - 1 for ids in by_name.values() if len(ids) > 1),
            "missing_items": missing,
            "unexpected_items": unexpected,
        }

    def _failed_payload(
        self,
        operation: AgentBatchOperation,
        existing: dict[str, AgentBatchItem],
        error_code: str,
        message: str,
    ) -> dict[str, Any]:
        items = [_item_view(item) for item in existing.values()]
        succeeded = sum(1 for item in items if item["status"] == _SUCCESS)
        failed = sum(1 for item in items if item["status"] == _FAILED)
        return {
            "ok": False,
            "action": operation.tool_name,
            "operation_id": operation.operation_id,
            "error_code": error_code,
            "message": message,
            "succeeded": succeeded,
            "failed": failed,
            "items": items,
            "verification": {
                "status": error_code,
                "expected_count": operation.expected_count,
                "actual_count": succeeded,
                "duplicate_count": 0,
                "missing_items": [item["client_item_id"] for item in items if item["status"] != _SUCCESS],
                "unexpected_items": [],
            },
        }
