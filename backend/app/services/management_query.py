"""Read-only management queries for the Management Agent tools.

Every method enforces RBAC via existing permission helpers and delegates to
ProjectService / TaskService / IssueService / ProgressService — never raw SQL.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.permissions import can_view_project, can_view_task
from app.models.issue import IssueStatus
from app.models.project import Project
from app.models.task import Task, TaskAiStatus, TaskStatus
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.dashboard import ManagementAttentionItem
from app.schemas.task import TaskPlanningFields
from app.services.action_item import ActionItemService
from app.services.business_clock import BusinessClock
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.issue import IssueService
from app.services.management_attention import ManagementAttentionService
from app.services.progress import ProgressService
from app.services.project import ProjectService
from app.services.task import TaskService

OwnerScope = Literal["me", "user", "all"]


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def project_payload(project: Project) -> dict[str, Any]:
    owner = project.owner
    owners = list(project.owners)
    if owner is not None and all(person.id != owner.id for person in owners):
        owners.append(owner)
    owners.sort(key=lambda person: (person.name, person.id))
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "goal": project.goal,
        "owner_id": project.owner_id,
        "owner_name": owner.name if owner else None,
        "owner_ids": [person.id for person in owners] or [project.owner_id],
        "owners": [
            {"id": person.id, "name": person.name, "username": person.username} for person in owners
        ],
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "target_date": project.target_date.isoformat() if project.target_date else None,
        "status": _enum_value(project.status),
        "risk_level": _enum_value(project.risk_level),
    }


# Backward-compatible alias for internal call sites.
_project_payload = project_payload


def task_payload(task: Task) -> dict[str, Any]:
    owner = task.owner
    project = task.project
    planned_due = task.due_date.isoformat() if task.due_date else None
    actual_finish = task.actual_finish_date.isoformat() if task.actual_finish_date else None
    return {
        **TaskPlanningFields.model_validate(task, from_attributes=True).model_dump(mode="json"),
        "branch_option_id": task.branch_option_id,
        "id": task.id,
        "project_id": task.project_id,
        "project_code": project.project_code if project else None,
        "project_name": project.project_name if project else None,
        "task_name": task.task_name,
        "work_stream": task.work_stream,
        "start_date": task.start_date.isoformat() if task.start_date else None,
        "progress_percent": task.progress_percent,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "branch_root_id": task.branch_root_id,
        "branch_label": task.branch_label,
        "is_active_branch": task.is_active_branch,
        "is_execution_active": task.is_execution_active,
        "owner_id": task.owner_id,
        "owner_name": owner.name if owner else None,
        # Legacy field kept for older clients; prefer planned_due_date in answers.
        "due_date": planned_due,
        "planned_due_date": planned_due,
        # Forecast comes from the scheduling engine; never invent one from due_date.
        "forecast_finish_date": None,
        "actual_finish_date": actual_finish,
        "date_semantics": {
            "planned_due_date": "计划截止日期（承诺/排期字段，不是引擎预测）",
            "forecast_finish_date": "引擎预测完成日；未调用排期预览时为 null，不得用计划截止日顶替",
            "actual_finish_date": "实际完成日（执行事实）",
        },
        "status": _enum_value(task.status),
        "ai_status": _enum_value(task.ai_status),
        "ai_risk_level": _enum_value(task.ai_risk_level),
        "version": int(getattr(task, "version", 1) or 1),
    }


_task_payload = task_payload


def issue_payload(issue: object) -> dict[str, Any]:
    from app.models.issue import Issue

    assert isinstance(issue, Issue)
    task = issue.task
    project = issue.project
    reporter = issue.reporter
    return {
        "id": issue.id,
        "project_id": issue.project_id,
        "project_code": project.project_code if project else None,
        "task_id": issue.task_id,
        "task_name": task.task_name if task else None,
        "title": issue.title,
        "description": issue.description,
        "severity": _enum_value(issue.severity),
        "status": _enum_value(issue.status),
        "reporter_name": reporter.name if reporter else None,
        "created_at": issue.created_at.isoformat(),
    }


_issue_payload = issue_payload


def action_item_payload(item: object) -> dict[str, Any]:
    from app.models.action_item import ActionItem

    assert isinstance(item, ActionItem)
    project = item.project
    owner = item.owner
    return {
        "id": item.id,
        "project_id": item.project_id,
        "project_code": project.project_code if project else None,
        "task_id": item.task_id,
        "task_name": item.task.task_name if item.task else None,
        "issue_id": item.issue_id,
        "issue_title": item.issue.title if item.issue else None,
        "title": item.title,
        "description": item.description,
        "owner_id": item.owner_id,
        "owner_name": owner.name if owner else None,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "status": _enum_value(item.status),
        "priority": _enum_value(item.priority),
        "created_at": item.created_at.isoformat(),
    }


def _attention_payload(item: ManagementAttentionItem) -> dict[str, Any]:
    return item.model_dump()


class ManagementQueryService:
    """RBAC-aware read queries exposed as Management Agent tools."""

    def __init__(self, db: Session, *, clock: BusinessClock | None = None) -> None:
        self.db = db
        self.projects = ProjectService(db)
        self.tasks = TaskService(db)
        self.issues = IssueService(db)
        self.action_items = ActionItemService(db)
        self.progress = ProgressService(db)
        self.management_attention = ManagementAttentionService(db)
        self.users = UserRepository(db)
        self.clock = clock or BusinessClock()

    def get_current_user(self, actor: User) -> dict[str, Any]:
        """Identity from the authenticated session — never from client-forged ids."""
        return {
            "ok": True,
            "action": "get_current_user",
            "user_id": actor.id,
            "name": actor.name,
            "username": actor.username,
            "role": actor.role.value if hasattr(actor.role, "value") else str(actor.role),
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "note": ("“我的任务”指本人负责（owner_id=当前用户），不等于“我能看到的全部任务”。"),
        }

    def get_project_progress_overview(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """A reproducible recent-progress definition; absence of facts is explicit."""
        from datetime import UTC

        from sqlalchemy import select

        from app.models.progress_update import ProgressUpdate

        if not project_id and not project_code:
            raise DomainValidationError("请指定项目编号或 ID")
        if not 1 <= days <= 90:
            raise DomainValidationError("统计窗口必须为 1–90 天")
        try:
            project = (
                self.projects.get_project(project_id)
                if project_id
                else self.projects.get_project_by_code((project_code or "").strip().upper())
            )
        except ProjectNotFoundError:
            return {"found": False, "project_code": project_code}
        self._ensure_project_visible(actor, project)
        tasks = [
            t for t in self._visible_tasks(actor, project_id=project.id) if t.is_execution_active
        ]
        now = self.clock.now()
        start = now - timedelta(days=days)
        ids = [t.id for t in tasks]
        updates = (
            list(
                self.db.scalars(
                    select(ProgressUpdate)
                    .where(
                        ProgressUpdate.task_id.in_(ids),
                        ProgressUpdate.created_at >= start.astimezone(UTC),
                        ProgressUpdate.created_at <= now.astimezone(UTC),
                    )
                    .order_by(ProgressUpdate.created_at, ProgressUpdate.id)
                )
            )
            if ids
            else []
        )
        covered = {u.task_id for u in updates}
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        delayed = [
            t
            for t in tasks
            if t.due_date
            and t.due_date < self.clock.today()
            and t.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}
        ]
        issues = self.list_open_issues(actor, project_id=project.id)
        issues_count = len(issues)
        return {
            "project": project_payload(project),
            "queried_at": now.isoformat(),
            "window": {
                "from": start.isoformat(),
                "to": now.isoformat(),
                "days": days,
                "timezone": self.clock.timezone,
                "definition": "最近 N×24 小时内提交的进度汇报；任务状态为查询时快照",
            },
            "counts": {
                "active_visible_tasks": len(tasks),
                "completed": len(completed),
                "overdue_unfinished": len(delayed),
                "open_issues": issues_count,
                "recent_updates": len(updates),
            },
            "coverage": {
                "tasks_with_recent_updates": len(covered),
                "tasks_without_recent_updates": len(tasks) - len(covered),
                "all_visible_tasks_scanned": True,
                "dependencies_evaluated": False,
            },
            "assessment": "有延期或未解决问题"
            if delayed or issues_count
            else "未发现这两类异常；不能据此断言项目顺利",
            "evidence": [
                {
                    "progress_id": u.id,
                    "task_id": u.task_id,
                    "created_at": u.created_at.isoformat(),
                    "progress_percent": u.progress_percent,
                    "summary": u.summary or u.raw_content[:300],
                }
                for u in updates[-100:]
            ],
            "evidence_truncated": len(updates) > 100,
            "limitations": [
                "不以任务平均完成度代表项目完成度",
                "未评估依赖关键路径",
                "没有近期汇报不代表没有进展",
            ],
        }

    def search_tasks(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
        owner_scope: OwnerScope = "all",
        owner_id: int | None = None,
        date_preset: str | None = None,
        due_from: date | str | None = None,
        due_to: date | str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        include_inactive: bool = False,
        statuses: list[str] | None = None,
        progress_min: int | None = None,
        progress_max: int | None = None,
        overdue: bool | None = None,
        limit: int = 50,
        cursor: int | None = None,
    ) -> dict[str, Any]:
        """Permission-filtered task search with backend-resolved date presets."""
        if owner_scope not in {"all", "user", "me"}:
            raise DomainValidationError("无效负责人范围")
        try:
            status_set = {TaskStatus(s) for s in statuses} if statuses else None
        except ValueError as exc:
            raise DomainValidationError("无效任务状态") from exc
        if any(v is not None and not 0 <= v <= 100 for v in (progress_min, progress_max)) or (progress_min is not None and progress_max is not None and progress_min > progress_max):
            raise DomainValidationError("完成度范围必须为 0–100 且下限不大于上限")
        limit = max(1, min(int(limit or 50), 100))
        resolved_project_id = project_id
        if resolved_project_id is None and project_code:
            try:
                resolved_project_id = self.projects.get_project_by_code(
                    project_code.strip().upper()
                ).id
            except ProjectNotFoundError:
                return self._empty_search(
                    actor,
                    applied={
                        "project_code": project_code,
                        "owner_scope": owner_scope,
                        "date_preset": date_preset,
                    },
                    note="未找到该项目编号，或当前账号不可见。",
                )

        try:
            due_range = self.clock.resolve_range(
                date_preset=date_preset, due_from=due_from, due_to=due_to
            )
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        if owner_scope == "me":
            owner_filter = actor.id
        elif owner_scope == "user":
            if owner_id is None:
                raise DomainValidationError("owner_scope=user 时必须提供 owner_id")
            owner_filter = int(owner_id)
        else:
            owner_filter = None

        status_filter: TaskStatus | None = None
        if status:
            try:
                status_filter = TaskStatus(status)
            except ValueError as exc:
                raise DomainValidationError(f"无效任务状态: {status}") from exc

        needle = (keyword or "").strip().lower() or None
        after_id = int(cursor) if cursor is not None else 0

        matched: list[Task] = []
        for task in self._visible_tasks(actor, project_id=resolved_project_id):
            if status_set and task.status not in status_set:
                continue
            if progress_min is not None and (task.progress_percent is None or task.progress_percent < progress_min):
                continue
            if progress_max is not None and (task.progress_percent is None or task.progress_percent > progress_max):
                continue
            is_overdue = bool(task.due_date and task.due_date < self.clock.today() and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELLED})
            if overdue is not None and is_overdue != overdue:
                continue
            if not include_inactive and not task.is_execution_active:
                continue
            if owner_filter is not None and task.owner_id != owner_filter:
                continue
            if status_filter is not None and task.status != status_filter:
                continue
            if due_range is not None:
                if task.due_date is None:
                    continue
                if task.due_date < due_range.start or task.due_date > due_range.end:
                    continue
            if needle:
                hay = " ".join(
                    part
                    for part in (
                        task.task_name,
                        task.work_stream or "",
                        task.owner.name if task.owner else "",
                        task.project.project_code if task.project else "",
                        task.project.project_name if task.project else "",
                    )
                ).lower()
                if needle not in hay:
                    continue
            matched.append(task)

        matched.sort(key=lambda item: item.id)
        remaining = [task for task in matched if task.id > after_id]
        page = remaining[:limit]
        next_cursor = page[-1].id if len(remaining) > limit else None
        items = [_task_payload(task) for task in page]
        applied = {
            "project_id": resolved_project_id,
            "project_code": project_code,
            "owner_scope": owner_scope,
            "owner_id": owner_filter,
            "status": status_filter.value if status_filter else None,
            "statuses": sorted(s.value for s in status_set) if status_set else None,
            "progress_min": progress_min,
            "progress_max": progress_max,
            "overdue": overdue,
            "keyword": keyword,
            "include_inactive": include_inactive,
            "limit": limit,
            "date_range": due_range.as_dict() if due_range else None,
        }
        coverage = {
            "returned": len(items),
            "total_matched": len(matched),
            "truncated": next_cursor is not None,
            "note": (
                "total_matched 是权限过滤后的命中数；若 truncated=true，不得把本页结果称为全部。"
            ),
        }
        return {
            "ok": True,
            "action": "search_tasks",
            "items": items,
            "total": len(matched),
            "next_cursor": next_cursor,
            "applied_filters": applied,
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "coverage": coverage,
        }

    def list_my_tasks(
        self,
        actor: User,
        *,
        date_preset: str | None = None,
        due_from: date | str | None = None,
        due_to: date | str | None = None,
        status: str | None = None,
        project_id: int | None = None,
        project_code: str | None = None,
        keyword: str | None = None,
        limit: int = 50,
        cursor: int | None = None,
    ) -> dict[str, Any]:
        """Same semantics as the “我的任务” page: tasks owned by the actor."""
        result = self.search_tasks(
            actor,
            project_id=project_id,
            project_code=project_code,
            owner_scope="me",
            date_preset=date_preset,
            due_from=due_from,
            due_to=due_to,
            status=status,
            keyword=keyword,
            limit=limit,
            cursor=cursor,
        )
        result["action"] = "list_my_tasks"
        return result

    def query_tasks(self, actor: User, request: dict[str, Any] | None = None) -> dict[str, Any]:
        """Generic task Query DSL on top of permission-scoped rows."""
        from app.agents.query import AgentQueryRequest, QueryPolicyValidator, apply_query

        parsed = AgentQueryRequest.model_validate(request or {})
        QueryPolicyValidator("task").validate(parsed)
        rows = list(self._visible_tasks(actor))
        result = apply_query(rows, parsed, entity="task", clock=self.clock)
        items = [
            task_payload(row) if not isinstance(row, dict) else row for row in result["items"]
        ]
        return {
            "ok": True,
            "action": "query_tasks",
            "items": items,
            "total": result["total"],
            "limit": result["limit"],
            "offset": result["offset"],
            "aggregated": result.get("aggregated", False),
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "coverage": {
                "returned": len(items),
                "total_matched": result["total"],
                "truncated": result["truncated"],
                "note": "权限过滤后由 Query DSL 求值；禁止将截断页称为全部。",
            },
        }

    def search_projects(self, actor: User, request: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.agents.query import AgentQueryRequest, QueryPolicyValidator, apply_query

        parsed = AgentQueryRequest.model_validate(request or {})
        QueryPolicyValidator("project").validate(parsed)
        rows = list(self._visible_projects(actor))
        result = apply_query(rows, parsed, entity="project", clock=self.clock)
        items = [
            _project_payload(row) if not isinstance(row, dict) else row for row in result["items"]
        ]
        return {
            "ok": True,
            "action": "search_projects",
            "items": items,
            "total": result["total"],
            "limit": result["limit"],
            "offset": result["offset"],
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "coverage": {
                "returned": len(items),
                "total_matched": result["total"],
                "truncated": result["truncated"],
            },
        }

    def search_issues(self, actor: User, request: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.agents.query import AgentQueryRequest, QueryPolicyValidator, apply_query

        parsed = AgentQueryRequest.model_validate(request or {})
        QueryPolicyValidator("issue").validate(parsed)
        # Visible issues = open issues across visible projects (same permission gate).
        rows = []
        for project in self._visible_projects(actor):
            rows.extend(self.issues.list_issues(actor, project_id=project.id))
        result = apply_query(rows, parsed, entity="issue", clock=self.clock)
        items = [
            _issue_payload(row) if not isinstance(row, dict) else row for row in result["items"]
        ]
        return {
            "ok": True,
            "action": "search_issues",
            "items": items,
            "total": result["total"],
            "limit": result["limit"],
            "offset": result["offset"],
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "coverage": {
                "returned": len(items),
                "total_matched": result["total"],
                "truncated": result["truncated"],
            },
        }

    def _empty_search(self, actor: User, *, applied: dict[str, Any], note: str) -> dict[str, Any]:
        return {
            "ok": True,
            "action": "search_tasks",
            "items": [],
            "total": 0,
            "next_cursor": None,
            "applied_filters": applied,
            "business_timezone": self.clock.timezone,
            "queried_at": self.clock.now().isoformat(),
            "coverage": {
                "returned": 0,
                "total_matched": 0,
                "truncated": False,
                "note": note,
            },
        }

    def _ensure_project_visible(self, actor: User, project: Project) -> None:
        if not can_view_project(self.db, actor, project):
            raise PermissionDeniedError

    def _ensure_task_visible(self, actor: User, task: Task) -> None:
        if not can_view_task(self.db, actor, task):
            raise PermissionDeniedError

    def _visible_projects(self, actor: User) -> list[Project]:
        return self.projects.list_projects(actor)

    def _visible_tasks(
        self,
        actor: User,
        *,
        project_id: int | None = None,
    ) -> list[Task]:
        projects = self._visible_projects(actor)
        if project_id is not None:
            projects = [project for project in projects if project.id == project_id]
        tasks: list[Task] = []
        for project in projects:
            for task in self.tasks.list_project_tasks(project.id):
                if can_view_task(self.db, actor, task):
                    tasks.append(task)
        return tasks

    def list_task_branches(self, actor: User, task_id: int) -> list[dict[str, Any]]:
        from app.services.task import TaskService

        service = TaskService(self.db)
        task = service.get_task(task_id)
        self._ensure_task_visible(actor, task)
        return [
            task_payload(item)
            for item in service.list_branch_siblings(task_id)
            if can_view_task(self.db, actor, item)
        ]

    def list_projects(self, actor: User) -> list[dict[str, Any]]:
        return [_project_payload(project) for project in self._visible_projects(actor)]

    def get_project(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
    ) -> dict[str, Any]:
        if project_id is None and project_code is None:
            msg = "project_id or project_code is required"
            raise ValueError(msg)
        try:
            project = (
                self.projects.get_project(project_id)
                if project_id is not None
                else self.projects.get_project_by_code(project_code or "")
            )
        except ProjectNotFoundError:
            return {"found": False}
        self._ensure_project_visible(actor, project)
        payload = _project_payload(project)
        payload["found"] = True
        return payload

    def list_project_tasks(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
        owner_name: str | None = None,
    ) -> list[dict[str, Any]]:
        if project_id is None and project_code is None:
            msg = "project_id or project_code is required"
            raise ValueError(msg)
        try:
            project = (
                self.projects.get_project(project_id)
                if project_id is not None
                else self.projects.get_project_by_code(project_code or "")
            )
        except ProjectNotFoundError:
            return []
        self._ensure_project_visible(actor, project)
        tasks = self.tasks.list_project_tasks(project.id)
        payloads = [_task_payload(task) for task in tasks if can_view_task(self.db, actor, task)]
        if owner_name:
            needle = owner_name.strip().lower()
            payloads = [
                item
                for item in payloads
                if item.get("owner_name") and needle in item["owner_name"].lower()
            ]
        return payloads

    def get_task_progress(
        self,
        actor: User,
        *,
        task_id: int | None = None,
        project_code: str | None = None,
    ) -> dict[str, Any]:
        if task_id is None and project_code is None:
            msg = "task_id or project_code is required"
            raise ValueError(msg)

        if task_id is not None:
            try:
                task = self.tasks.get_task(task_id)
            except TaskNotFoundError:
                return {"found": False}
            self._ensure_task_visible(actor, task)
            return self._task_progress_payload(actor, task)

        try:
            project = self.projects.get_project_by_code(project_code or "")
        except ProjectNotFoundError:
            return {"found": False}
        self._ensure_project_visible(actor, project)
        tasks = [
            task
            for task in self.tasks.list_project_tasks(project.id)
            if can_view_task(self.db, actor, task)
        ]
        if not tasks:
            return {"found": True, "project": _project_payload(project), "tasks": []}
        return {
            "found": True,
            "project": _project_payload(project),
            "tasks": [self._task_progress_payload(actor, task) for task in tasks],
        }

    def _task_progress_payload(self, actor: User, task: Task) -> dict[str, Any]:
        progress_rows = self.progress.list_task_progress(task.id)
        open_issues = self.issues.list_issues(
            actor,
            task_id=task.id,
            status=IssueStatus.OPEN,
        )
        payload = _task_payload(task)
        payload["found"] = True
        payload["recent_progress"] = [
            {
                "id": row.id,
                "summary": row.summary,
                "raw_content": row.raw_content,
                "ai_status": _enum_value(row.ai_status),
                "created_at": row.created_at.isoformat(),
            }
            for row in progress_rows[:5]
        ]
        payload["open_issues"] = [_issue_payload(issue) for issue in open_issues]
        return payload

    def list_delayed_tasks(
        self,
        actor: User,
        *,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        today = self.clock.today()
        results: list[dict[str, Any]] = []
        for task in self._visible_tasks(actor, project_id=project_id):
            if not task.is_execution_active:
                continue
            delayed = task.ai_status == TaskAiStatus.DELAYED or (
                task.due_date is not None and task.due_date < today
            )
            if delayed:
                results.append(_task_payload(task))
        return results

    def list_at_risk_tasks(
        self,
        actor: User,
        *,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for task in self._visible_tasks(actor, project_id=project_id):
            if not task.is_execution_active:
                continue
            if task.ai_status == TaskAiStatus.AT_RISK:
                results.append(_task_payload(task))
        return results

    def list_open_issues(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        task_id: int | None = None,
    ) -> list[dict[str, Any]]:
        issues = self.issues.list_issues(
            actor,
            project_id=project_id,
            task_id=task_id,
            status=IssueStatus.OPEN,
        )
        return [_issue_payload(issue) for issue in issues]

    def list_action_items(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        project_code: str | None = None,
        owner_name: str | None = None,
        issue_id: int | None = None,
        open_only: bool = True,
    ) -> list[dict[str, Any]]:
        resolved_project_id = project_id
        if resolved_project_id is None and project_code:
            try:
                resolved_project_id = self.projects.get_project_by_code(
                    project_code.strip().upper()
                ).id
            except ProjectNotFoundError:
                return []

        items = self.action_items.list_action_items(
            actor,
            project_id=resolved_project_id,
            issue_id=issue_id,
            open_only=open_only,
        )
        payloads = [action_item_payload(item) for item in items]
        if owner_name:
            needle = owner_name.strip().lower()
            payloads = [
                item
                for item in payloads
                if item.get("owner_name") and needle in item["owner_name"].lower()
            ]
        return payloads

    def get_management_attention_items(
        self,
        actor: User,
        *,
        today: date | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        items = self.management_attention.get_management_attention_items(
            actor,
            today=today or self.clock.today(),
            now=now or self.clock.now(),
        )
        return [_attention_payload(item) for item in items]

    def list_tasks_by_owner_name(self, actor: User, owner_name: str) -> list[dict[str, Any]]:
        """Helper for owner-name queries across visible projects."""
        needle = owner_name.strip().lower()
        if not needle:
            return []
        results: list[dict[str, Any]] = []
        for task in self._visible_tasks(actor):
            owner = task.owner
            if owner and needle in owner.name.lower():
                results.append(_task_payload(task))
        return results

    def list_upcoming_deadlines(
        self,
        actor: User,
        *,
        days: int = 7,
        date_preset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Upcoming due dates. Prefer date_preset=next_7_days / this_week over raw days."""
        if date_preset:
            due_range = self.clock.resolve_preset(date_preset)
            start, end = due_range.start, due_range.end
        else:
            today = self.clock.today()
            # Inclusive window of `days` calendar days starting today.
            start = today
            end = today + timedelta(days=max(days, 1) - 1)
        results: list[dict[str, Any]] = []
        for task in self._visible_tasks(actor):
            if not task.is_execution_active:
                continue
            if task.due_date is None:
                continue
            if start <= task.due_date <= end:
                results.append(_task_payload(task))
        results.sort(key=lambda item: item["due_date"] or "")
        return results
