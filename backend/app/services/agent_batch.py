"""Batch user resolve and transactional task writes for structured Agent intents."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.owner_labels import is_pending_owner_label
from app.core.permissions import can_create_task, can_modify_task_core
from app.models.agent_batch import AgentBatchItem, AgentBatchOperation
from app.models.planning import ProjectMember, TaskParticipant
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

_BATCH_CREATE_SUPPORTED = frozenset(
    {
        "client_item_id",
        "task_name",
        "title",
        "owner_name",
        "owner_names",
        "owners",
        "owner_id",
        "owner_ids",
        "collaborator_names",
        "collaborators",
        "collaborator_ids",
        "work_stream",
        "start_date",
        "due_date",
        "planned_duration_days",
        "description",
        "deliverable",
        "acceptance_criteria",
    }
)
_BATCH_CREATE_UNSUPPORTED = frozenset(
    {
        "is_milestone",
        "milestone",
        "milestone_name",
        "depends_on_task",
        "dependency",
        "dependencies",
        "predecessor",
        "link_type",
    }
)
_NAME_SPLIT = re.compile(r"[,，、/;；|]+")


def _split_names(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in _NAME_SPLIT.split(value) if part.strip()]
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            names.extend(_split_names(item))
        return names
    text = str(value).strip()
    return [text] if text else []


def _coerce_id_list(value: Any) -> list[int]:
    ids: list[int] = []
    if value is None:
        return ids
    raw = value if isinstance(value, list) else [value]
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
            continue
        text = str(item).strip()
        if text.isdigit():
            ids.append(int(text))
    return ids


def _normalize_create_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept common model aliases before validation / persistence."""
    row = dict(raw)
    if not str(row.get("task_name") or "").strip():
        title = str(row.get("title") or "").strip()
        if title:
            row["task_name"] = title
    # Resolved $ref values often land in *_names as integers; move to *_ids.
    name_ids = _coerce_id_list(row.get("owner_names") or row.get("owners"))
    if name_ids:
        merged = list(row.get("owner_ids") or [])
        merged.extend(name_ids)
        row["owner_ids"] = list(dict.fromkeys(int(v) for v in merged))
        # Drop non-name leftovers so people lookup does not see "123".
        kept_names = [
            item
            for item in (row.get("owner_names") or row.get("owners") or [])
            if not (
                isinstance(item, int)
                or (isinstance(item, str) and item.strip().isdigit())
            )
        ]
        if "owner_names" in row:
            row["owner_names"] = kept_names
        if "owners" in row:
            row["owners"] = kept_names
    collab_ids = _coerce_id_list(row.get("collaborator_names") or row.get("collaborators"))
    if collab_ids:
        merged = list(row.get("collaborator_ids") or [])
        merged.extend(collab_ids)
        row["collaborator_ids"] = list(dict.fromkeys(int(v) for v in merged))
        kept = [
            item
            for item in (row.get("collaborator_names") or row.get("collaborators") or [])
            if not (
                isinstance(item, int)
                or (isinstance(item, str) and item.strip().isdigit())
            )
        ]
        if "collaborator_names" in row:
            row["collaborator_names"] = kept
        if "collaborators" in row:
            row["collaborators"] = kept
    return row


def _collaborator_names(row: dict[str, Any]) -> list[str]:
    return _split_names(row.get("collaborator_names") or row.get("collaborators") or [])


def _owner_names(row: dict[str, Any]) -> list[str]:
    for key in ("owner_names", "owners"):
        if key in row and row[key] not in (None, ""):
            return [
                name
                for name in _split_names(row[key])
                if name and not name.isdigit()
            ]
    if row.get("owner_name") not in (None, ""):
        return [
            name
            for name in _split_names(row.get("owner_name"))
            if name and not name.isdigit()
        ]
    return []


def _people_names(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in items:
        for name in _owner_names(row):
            if name and not is_pending_owner_label(name):
                names.append(name)
        for collab in _collaborator_names(row):
            if collab and not is_pending_owner_label(collab):
                names.append(collab)
    return names


def _resolve_owner_ids(raw: dict[str, Any], resolved: dict[str, Any]) -> list[int]:
    """Primary owner first; additional owners are equal co-owners."""
    ids: list[int] = []
    if raw.get("owner_ids"):
        ids.extend(_coerce_id_list(raw["owner_ids"]))
    elif raw.get("owner_id") is not None:
        ids.extend(_coerce_id_list(raw["owner_id"]))
    for name in _owner_names(raw):
        if not name or is_pending_owner_label(name):
            continue
        hit = resolved.get(name)
        if hit:
            ids.append(int(hit["user_id"]))
    return list(dict.fromkeys(ids))


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
        names = _people_names(items)
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
            owner_ids = _resolve_owner_ids(raw, resolved)
            if owner_ids:
                owner_id = owner_ids[0]
            duration = raw.get("planned_duration_days")
            planned_duration = int(duration) if duration not in (None, "") else None
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
                        planned_duration_days=planned_duration,
                        description=_optional_str(raw, "description"),
                        deliverable=_optional_str(raw, "deliverable"),
                        acceptance_criteria=_optional_str(raw, "acceptance_criteria"),
                    ),
                )
            )

        if invalid:
            operation.status = "VALIDATION_FAILED"
            self.db.commit()
            return self._failed_payload(operation, existing, "VALIDATION_FAILED", "批量创建未写入：存在无法解析的条目")

        created_ids: list[int] = []
        try:
            from app.services.entity_codes import allocate_task_codes

            to_create = [(raw, row, payload) for raw, row, payload in prepared if payload is not None]
            codes = allocate_task_codes(self.db, len(to_create)) if to_create else []
            verification: dict[str, Any] = {
                "status": _SUCCESS,
                "expected_count": len(items),
                "actual_count": 0,
                "created_task_ids": [],
                "duplicate_count": 0,
                "missing_items": [],
                "unexpected_items": [],
                "field_diffs": [],
            }
            with self.db.begin_nested():
                for (raw, row, payload), task_code in zip(to_create, codes, strict=True):
                    payload.task_code = task_code
                    task = self.tasks.create_task(project.id, payload, actor=actor)
                    self.db.flush()
                    self._attach_people(project.id, task.id, raw, resolved)
                    row.status = _SUCCESS
                    row.resource_id = str(task.id)
                    row.error_code = None
                    row.error_message = None
                    created_ids.append(task.id)
                verification = self._verify_create(project.id, operation.operation_id, items, existing)
                if verification["status"] == "VALIDATION_FAILED":
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
        operation.details = {"created_ids": created_ids, "verification": verification}
        self.db.commit()
        reviewed = verification.get("status") == "NEEDS_REVIEW"
        # Writes already committed: keep ok=True so the executor does not mark FAILED.
        return {
            "ok": True,
            "needs_review": reviewed,
            "action": "batch_create_tasks",
            "operation_id": operation.operation_id,
            "created_task_count": len(created_ids),
            "items": [_item_view(existing[str(row["client_item_id"])]) for row in items],
            "verification": verification,
            "message": ("任务已写入，但回读核对发现字段差异，请核实" if reviewed else None),
        }

    def batch_update_tasks(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        items = self._incoming_items(args)
        operation = self._operation(actor, args, "batch_update_tasks", expected=len(items))
        existing = self._items_by_client(operation.operation_id)
        names = _people_names(items)
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
        items = args.get("items")
        if items in (None, [], ""):
            items = args.get("tasks")
        if isinstance(items, str):
            text = items.strip()
            if not text:
                raise DomainValidationError("items 不能为空")
            try:
                items = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DomainValidationError("items 必须是数组或 JSON 数组字符串") from exc
        if not isinstance(items, list) or not items:
            raise DomainValidationError("items 不能为空")
        if len(items) > _MAX_ITEMS:
            raise DomainValidationError(f"单次最多 {_MAX_ITEMS} 条")
        seen: set[str] = set()
        normalized = []
        for index, raw in enumerate(items):
            payload = _normalize_create_row(dict(raw or {}))
            client_id = str(payload.get("client_item_id") or "").strip()
            if not client_id:
                client_id = f"auto_{index + 1}"
                payload["client_item_id"] = client_id
            if client_id in seen:
                raise DomainValidationError(f"client_item_id 重复：{client_id}")
            seen.add(client_id)
            normalized.append(payload)
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
        unsupported = sorted(set(raw) & _BATCH_CREATE_UNSUPPORTED)
        if unsupported:
            return {
                "error_code": "CAPABILITY_UNSUPPORTED",
                "message": (
                    "批量创建任务暂不支持字段 "
                    + "、".join(unsupported)
                    + "；请改用专用里程碑/依赖工具或去掉这些字段后重试"
                ),
            }
        unknown = sorted(set(raw) - _BATCH_CREATE_SUPPORTED)
        if unknown:
            return {
                "error_code": "INVALID_ARGUMENTS",
                "message": "批量创建任务包含未知字段：" + "、".join(unknown),
            }
        name = str(raw.get("task_name") or "").strip()
        if not name:
            return {"error_code": "INVALID_ARGUMENTS", "message": "task_name 必填"}
        duration = raw.get("planned_duration_days")
        if duration not in (None, ""):
            try:
                if int(duration) < 1:
                    return {
                        "error_code": "INVALID_ARGUMENTS",
                        "message": "planned_duration_days 必须 ≥ 1",
                    }
            except (TypeError, ValueError):
                return {
                    "error_code": "INVALID_ARGUMENTS",
                    "message": "planned_duration_days 必须是整数",
                }
        people = []
        for name in _owner_names(raw):
            if name and not is_pending_owner_label(name):
                people.append(name)
        people.extend(
            name
            for name in _collaborator_names(raw)
            if name and not is_pending_owner_label(name)
        )
        for person in people:
            if person in missing or person not in resolved:
                return {
                    "error_code": "OWNER_NOT_FOUND",
                    "message": f"未找到唯一匹配用户: {person}",
                }
            if person in ambiguous:
                return {
                    "error_code": "AMBIGUOUS_ENTITY",
                    "message": f"人员重名: {person}",
                }
        exists = self.db.scalar(
            select(Task.id).where(Task.project_id == project.id, Task.task_name == name)
        )
        if exists:
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

    def _ensure_project_member(self, project_id: int, user_id: int) -> None:
        member = self.db.get(ProjectMember, (project_id, user_id))
        if member is None:
            self.db.add(
                ProjectMember(
                    project_id=project_id,
                    user_id=user_id,
                    role="CONTRIBUTOR",
                    receive_notifications=True,
                    is_active=True,
                )
            )
        elif not member.is_active:
            member.is_active = True

    def _attach_participant(self, task_id: int, user_id: int, role: str) -> None:
        participant = self.db.get(TaskParticipant, (task_id, user_id))
        if participant is None:
            self.db.add(TaskParticipant(task_id=task_id, user_id=user_id, role=role))
        elif role == "OWNER" and participant.role != "OWNER":
            # Co-owner outranks collaborator/watcher when both appear in input.
            participant.role = "OWNER"

    def _attach_people(
        self,
        project_id: int,
        task_id: int,
        raw: dict[str, Any],
        resolved: dict[str, Any],
    ) -> None:
        owner_ids = _resolve_owner_ids(raw, resolved)
        # Primary owner lives on tasks.owner_id; additional equal owners use OWNER role.
        for user_id in owner_ids[1:]:
            self._ensure_project_member(project_id, user_id)
            self._attach_participant(task_id, user_id, "OWNER")

        collab_ids: list[int] = []
        for name in _collaborator_names(raw):
            if not name or is_pending_owner_label(name):
                continue
            hit = resolved.get(name)
            if hit:
                collab_ids.append(int(hit["user_id"]))
        for value in raw.get("collaborator_ids") or []:
            collab_ids.append(int(value))
        owner_set = set(owner_ids)
        for user_id in dict.fromkeys(collab_ids):
            if user_id in owner_set:
                continue
            self._ensure_project_member(project_id, user_id)
            self._attach_participant(task_id, user_id, "COLLABORATOR")

    def _verify_create(
        self,
        project_id: int,
        operation_id: str,
        items: list[dict[str, Any]],
        existing: dict[str, AgentBatchItem],
    ) -> dict[str, Any]:
        field_diffs: list[dict[str, Any]] = []
        missing_items: list[str] = []
        created_ids: list[int] = []
        for raw in items:
            client_id = str(raw["client_item_id"])
            row = existing.get(client_id)
            if row is None or not row.resource_id:
                missing_items.append(str(raw.get("task_name") or client_id))
                continue
            task = self.db.get(Task, int(row.resource_id))
            if task is None or task.project_id != project_id:
                field_diffs.append(
                    {
                        "client_item_id": client_id,
                        "field": "resource",
                        "expected": "task in project",
                        "actual": None,
                    }
                )
                missing_items.append(str(raw.get("task_name") or client_id))
                continue
            created_ids.append(task.id)
            expected_name = str(raw["task_name"]).strip()
            if task.task_name != expected_name:
                field_diffs.append(
                    {
                        "client_item_id": client_id,
                        "field": "task_name",
                        "expected": expected_name,
                        "actual": task.task_name,
                    }
                )
            expected_stream = _optional_str(raw, "work_stream")
            if expected_stream is not None and (task.work_stream or None) != expected_stream:
                field_diffs.append(
                    {
                        "client_item_id": client_id,
                        "field": "work_stream",
                        "expected": expected_stream,
                        "actual": task.work_stream,
                    }
                )
            expected_start = _parse_date(raw.get("start_date"), field="start_date")
            if expected_start is not None and task.start_date != expected_start:
                field_diffs.append(
                    {
                        "client_item_id": client_id,
                        "field": "start_date",
                        "expected": expected_start.isoformat(),
                        "actual": task.start_date.isoformat() if task.start_date else None,
                    }
                )
            expected_due = _parse_date(raw.get("due_date"), field="due_date")
            if expected_due is not None and task.due_date != expected_due:
                field_diffs.append(
                    {
                        "client_item_id": client_id,
                        "field": "due_date",
                        "expected": expected_due.isoformat(),
                        "actual": task.due_date.isoformat() if task.due_date else None,
                    }
                )
            duration = raw.get("planned_duration_days")
            if duration not in (None, ""):
                if task.planned_duration_days != int(duration):
                    field_diffs.append(
                        {
                            "client_item_id": client_id,
                            "field": "planned_duration_days",
                            "expected": int(duration),
                            "actual": task.planned_duration_days,
                        }
                    )
            # When only names are present, resolve expected names against primary + OWNER rows.
            expected_owner_names = [
                name for name in _owner_names(raw) if name and not is_pending_owner_label(name)
            ]
            if raw.get("owner_ids"):
                expected_ids = [int(value) for value in raw["owner_ids"]]
                actual_ids = {task.owner_id} if task.owner_id is not None else set()
                actual_ids.update(
                    row.user_id
                    for row in self.db.scalars(
                        select(TaskParticipant).where(
                            TaskParticipant.task_id == task.id,
                            TaskParticipant.role == "OWNER",
                        )
                    )
                )
                for expected in expected_ids:
                    if expected not in actual_ids:
                        field_diffs.append(
                            {
                                "client_item_id": client_id,
                                "field": "owner_ids",
                                "expected": expected,
                                "actual": sorted(x for x in actual_ids if x is not None),
                            }
                        )
            elif raw.get("owner_id") is not None and not expected_owner_names:
                if task.owner_id != int(raw["owner_id"]):
                    field_diffs.append(
                        {
                            "client_item_id": client_id,
                            "field": "owner_id",
                            "expected": int(raw["owner_id"]),
                            "actual": task.owner_id,
                        }
                    )
            elif expected_owner_names:
                actual_names: set[str] = set()
                if task.owner is not None:
                    actual_names.add(task.owner.name)
                owner_rows = list(
                    self.db.scalars(
                        select(TaskParticipant).where(
                            TaskParticipant.task_id == task.id,
                            TaskParticipant.role == "OWNER",
                        )
                    )
                )
                for row in owner_rows:
                    user = self.db.get(User, row.user_id)
                    if user is not None:
                        actual_names.add(user.name)
                for name in expected_owner_names:
                    if name not in actual_names:
                        field_diffs.append(
                            {
                                "client_item_id": client_id,
                                "field": "owner_names",
                                "expected": name,
                                "actual": sorted(actual_names),
                            }
                        )
            collab_names = [
                name for name in _collaborator_names(raw) if name and not is_pending_owner_label(name)
            ]
            if collab_names:
                participants = list(
                    self.db.scalars(
                        select(TaskParticipant).where(
                            TaskParticipant.task_id == task.id,
                            TaskParticipant.role == "COLLABORATOR",
                        )
                    )
                )
                actual_ids = {row.user_id for row in participants}
                for name in collab_names:
                    user = self.db.scalar(
                        select(User).where(User.name == name, User.status == UserStatus.ACTIVE)
                    )
                    if user is None or user.id not in actual_ids:
                        field_diffs.append(
                            {
                                "client_item_id": client_id,
                                "field": "collaborator_names",
                                "expected": name,
                                "actual": sorted(actual_ids),
                            }
                        )
        status = (
            _SUCCESS
            if not missing_items and not field_diffs
            else ("NEEDS_REVIEW" if created_ids and field_diffs else "VALIDATION_FAILED")
        )
        return {
            "status": status,
            "expected_count": len(items),
            "actual_count": len(created_ids),
            "created_task_ids": created_ids,
            "duplicate_count": 0,
            "missing_items": missing_items,
            "unexpected_items": [],
            "field_diffs": field_diffs,
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
