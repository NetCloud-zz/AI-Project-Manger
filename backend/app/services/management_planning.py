"""Agent-facing planning, change and notification operations.

Every method reuses the same domain services, permissions and validation as the
REST endpoints. The assistant can draft, simulate and propose. Publishing a plan
draft still requires the user in the UI. Confirming a change proposal also
requires the user on the proposal card; ``execute_change_plan`` may apply only
after that same user has confirmed (status=CONFIRMED, confirmed_by=actor).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.owner_labels import is_pending_owner_label
from app.core.permissions import (
    can_modify_project,
    can_request_issue_advice,
    can_submit_progress,
    can_view_issue,
    can_view_project,
    can_view_task,
)
from app.models.change_proposal import ChangeProposal
from app.models.issue import Issue, IssueStatus
from app.models.progress_update import ProgressUpdate
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.change_proposal import ChangeRequest, ProposalCreate, ProposalRevision
from app.schemas.plan_draft import (
    PlanDraftContent,
    PlanDraftCreate,
    PlanDraftRevision,
    PlanDraftUpdate,
)
from app.schemas.progress import ProgressSubmit
from app.schemas.scheduling import SchedulePreviewInput
from app.services.change_proposal import ChangeProposalService
from app.services.exceptions import (
    DomainValidationError,
    PermissionDeniedError,
    ProjectNotFoundError,
    TaskNotFoundError,
)
from app.services.advice import AdviceService
from app.services.business_clock import BusinessClock
from app.services.notification_delivery import NotificationDeliveryService
from app.services.plan_draft import PlanDraftService
from app.services.planning import PlanningService, record
from app.services.progress import ProgressService
from app.services.project import ProjectService
from app.services.project_context import ProjectContextService
from app.services.risk_event import RiskEventService, open_risk_summary
from app.services.scheduling import SchedulingService

#: Cap conversational payloads; the assistant asks for detail per object.
MAX_TASKS = 200
MAX_ROWS = 30


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


class ManagementPlanningService:
    """Planning tools for the assistant. The caller commits."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.planning = PlanningService(db)
        self.drafts = PlanDraftService(db)
        self.proposals = ChangeProposalService(db)
        self.notifications = NotificationDeliveryService(db)

    # ------------------------------------------------------------- resolving

    def project(self, *, project_id: int | None, project_code: str | None) -> Project:
        if project_id is not None:
            project = self.db.get(Project, int(project_id))
        elif project_code:
            project = self.db.scalar(
                select(Project).where(Project.project_code == project_code.strip().upper())
            )
        else:
            raise DomainValidationError("请提供 project_id 或 project_code")
        if project is None:
            raise ProjectNotFoundError
        return project

    # -------------------------------------------------------------- contexts

    def get_project_context(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Structured, permission-filtered facts for one project."""
        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        context = self.planning.context(project.id, actor)
        full = context["full_access"]
        tasks = context["tasks"]
        visible_ids = {task["id"] for task in tasks}
        issues = [
            {
                "id": issue.id,
                "task_id": issue.task_id,
                "title": issue.title,
                "severity": issue.severity.value,
                "status": issue.status.value,
                "created_at": _iso(issue.created_at),
            }
            for issue in self.db.scalars(
                select(Issue)
                .where(Issue.project_id == project.id, Issue.status != IssueStatus.RESOLVED)
                .order_by(Issue.created_at.desc())
                .limit(MAX_ROWS)
            )
            if issue.task_id is None or issue.task_id in visible_ids
        ]
        progress = [
            {
                "task_id": item.task_id,
                "task_name": item.task.task_name if item.task else None,
                "user_name": item.user.name if item.user else None,
                "summary": item.summary or item.raw_content[:200],
                "created_at": _iso(item.created_at),
            }
            for item in self.db.scalars(
                select(ProgressUpdate)
                .join(Task, Task.id == ProgressUpdate.task_id)
                .where(Task.project_id == project.id)
                .order_by(ProgressUpdate.created_at.desc())
                .limit(MAX_ROWS)
            )
            if item.task_id in visible_ids
        ]
        return {
            "project": {
                "id": project.id,
                "project_code": project.project_code,
                "project_name": project.project_name,
                "goal": project.goal,
                "status": project.status.value,
                "risk_level": project.risk_level.value,
                "start_date": _iso(project.start_date),
                "target_date": _iso(project.target_date),
                "owner_ids": [owner.id for owner in project.owners] or [project.owner_id],
                "owner_names": [owner.name for owner in project.owners]
                or [self.planning.user_name(project.owner_id)],
            },
            "access": {
                "full_project_facts": full,
                "can_propose_changes": can_modify_project(actor, project, self.db),
                "visible_task_count": len(tasks),
                "coverage": (
                    "全项目" if full else "仅本人负责或参与的任务；项目整体计划字段未包含在内"
                ),
            },
            "calendar": context["calendar"],
            "members": context["members"],
            "tasks": [
                {
                    key: _iso(task.get(key))
                    for key in (
                        "id",
                        "task_name",
                        "owner_id",
                        "work_stream",
                        "status",
                        "start_date",
                        "due_date",
                        "planned_duration_days",
                        "remaining_duration_days",
                        "actual_start_date",
                        "actual_finish_date",
                        "earliest_start_date",
                        "fixed_start_date",
                        "fixed_due_date",
                        "milestone_id",
                        "is_active_branch",
                        "ai_status",
                    )
                }
                for task in tasks[:MAX_TASKS]
            ],
            "task_owner_names": {
                str(task["id"]): self.planning.user_name(task["owner_id"]) for task in tasks
            },
            "milestones": context["milestones"],
            "routes": self._routes(context),
            "links": context["links"],
            "plan_versions": context["versions"][:10],
            "open_issues": issues,
            "recent_progress": progress,
            "open_proposals": self._open_proposals(project.id, actor),
            "open_risk_summary": open_risk_summary(self.db, project.id),
            "truncated": len(context["tasks"]) > MAX_TASKS,
        }

    @staticmethod
    def _routes(context: dict[str, Any]) -> list[dict[str, Any]]:
        options = context["branch_options"]
        return [
            {
                "group_id": group["id"],
                "name": group["name"],
                "entry_task_id": group["entry_task_id"],
                "exit_task_id": group["exit_task_id"],
                "options": [
                    {
                        "option_id": option["id"],
                        "name": option["name"],
                        "is_selected": option["is_selected"],
                        "task_ids": option["task_ids"],
                    }
                    for option in options
                    if option["group_id"] == group["id"]
                ],
            }
            for group in context["branch_groups"]
        ]

    def _open_proposals(self, project_id: int, actor: User) -> list[dict[str, Any]]:
        project = self.db.get(Project, project_id)
        if project is None or not can_modify_project(actor, project, self.db):
            return []
        rows = self.db.scalars(
            select(ChangeProposal)
            .where(
                ChangeProposal.project_id == project_id,
                ChangeProposal.status.in_(["DRAFT", "VALIDATED", "CONFIRMED"]),
            )
            .order_by(ChangeProposal.created_at.desc())
            .limit(10)
        )
        return [
            {
                "proposal_id": row.id,
                "status": row.status,
                "revision": row.revision,
                "reason": row.reason,
            }
            for row in rows
        ]

    def get_dependency_graph(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        context = self.planning.context(project.id, actor)
        if not context["full_access"]:
            raise PermissionDeniedError("只有本项目负责人、管理员或管理层可以查看完整依赖图")
        tasks = context["tasks"]
        return {
            "project_id": project.id,
            "project_code": project.project_code,
            "tasks": [
                {
                    "id": task["id"],
                    "task_name": task["task_name"],
                    "status": task["status"],
                    "start_date": _iso(task["start_date"]),
                    "due_date": _iso(task["due_date"]),
                    "planned_duration_days": task["planned_duration_days"],
                    "is_active_branch": task["is_active_branch"],
                    "in_execution": task["is_active_branch"]
                    and task["status"] in ("TODO", "IN_PROGRESS"),
                }
                for task in tasks[:MAX_TASKS]
            ],
            "links": [
                {
                    "source_id": link["source_id"],
                    "target_id": link["target_id"],
                    "link_type": link["link_type"],
                    "lag_days": link["lag_days"],
                }
                for link in context["links"]
            ],
            "milestones": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "target_date": _iso(row["target_date"]),
                    "status": row["status"],
                }
                for row in context["milestones"]
            ],
            "routes": self._routes(context),
            "note": "未选中的备用路线任务不计入执行统计；日期为当前保存计划，不是预测结果。",
        }

    # ---------------------------------------------------------- plan drafting

    def draft_project_plan(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        plan = self._resolve_plan_owners(args.get("plan") or {})
        content = PlanDraftContent.model_validate(plan)
        result = self.drafts.create(
            PlanDraftCreate(
                title=str(args.get("title") or content.project.project_name)[:200],
                content=content,
                idempotency_key=self._key(args),
            ),
            actor,
        )
        self.db.commit()
        return self._draft_result(result, "draft_project_plan")

    def update_project_plan_draft(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        draft_id = str(args["draft_id"])
        current = self.drafts.get(draft_id, actor)
        plan = self._resolve_plan_owners(args.get("plan") or {})
        content = PlanDraftContent.model_validate(plan)
        result = self.drafts.update(
            draft_id,
            PlanDraftUpdate(
                title=str(args.get("title") or current["title"])[:200],
                content=content,
                expected_revision=int(args.get("expected_revision") or current["revision"]),
            ),
            actor,
        )
        self.db.commit()
        return self._draft_result(result, "update_project_plan_draft")

    def review_project_plan_draft(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        draft_id = str(args["draft_id"])
        current = self.drafts.get(draft_id, actor)
        result = self.drafts.review(
            draft_id,
            PlanDraftRevision(
                expected_revision=int(args.get("expected_revision") or current["revision"])
            ),
            actor,
        )
        self.db.commit()
        return self._draft_result(result, "review_project_plan_draft")

    def validate_project_plan(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        return self.review_project_plan_draft(actor, args)

    def apply_project_plan(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        from app.schemas.plan_draft import PlanDraftPublish

        draft_id = str(args["draft_id"])
        current = self.drafts.get(draft_id, actor)
        body = PlanDraftPublish(
            digest=str(args["digest"]),
            expected_revision=int(args.get("expected_revision") or current["revision"]),
            idempotency_key=self._key(args),
        )
        result = self.drafts.publish(draft_id, body, actor)
        self.db.commit()
        payload = self._draft_result(result, "apply_project_plan")
        review = result.get("review") or {}
        expected = int(review.get("task_count") or 0)
        created = 0
        if result.get("result") and isinstance(result["result"], dict):
            created = len(result["result"].get("task_id_map") or result["result"].get("tasks") or [])
        if result.get("status") != "PUBLISHED":
            payload["ok"] = False
            payload["error_code"] = "VALIDATION_FAILED"
            payload["message"] = result.get("failure_reason") or "草案尚未发布"
            payload["verification"] = {
                "status": "VALIDATION_FAILED",
                "expected_count": expected,
                "actual_count": created,
                "duplicate_count": 0,
            }
            return payload
        payload["verification"] = {
            "status": "SUCCESS" if (expected == 0 or created == expected) else "VALIDATION_FAILED",
            "expected_count": expected,
            "actual_count": created,
            "duplicate_count": 0,
        }
        if payload["verification"]["status"] != "SUCCESS":
            payload["ok"] = False
            payload["error_code"] = "VALIDATION_FAILED"
            payload["message"] = "发布后校验未通过"
        return payload

    def _resolve_plan_owners(self, plan: dict[str, Any]) -> dict[str, Any]:
        from app.services.management_write import ManagementWriteService

        data = dict(plan)
        project = dict(data.get("project") or {})
        tasks = [dict(item) for item in (data.get("tasks") or [])]
        names: list[str] = []
        if project.get("owner_name") and not project.get("owner_id"):
            pname = str(project["owner_name"]).strip()
            if not is_pending_owner_label(pname):
                names.append(pname)
        for task in tasks:
            if task.get("owner_name") and not task.get("owner_id"):
                name = str(task["owner_name"]).strip()
                if is_pending_owner_label(name):
                    continue
                names.append(name)
        people = ManagementWriteService(self.db, auto_commit=False).find_users(names=names)
        resolved = {row["input"]: row["user_id"] for row in people.get("resolved", [])}
        questions = list(data.get("open_questions") or [])
        if project.get("owner_name") and not project.get("owner_id"):
            pname = str(project["owner_name"]).strip()
            if is_pending_owner_label(pname):
                questions.append("请补充项目负责人")
            else:
                owner_id = resolved.get(pname)
                if owner_id:
                    project["owner_id"] = owner_id
                else:
                    questions.append(f"请确认项目负责人：{project['owner_name']}")
        for task in tasks:
            if task.get("owner_name") and not task.get("owner_id"):
                name = str(task["owner_name"]).strip()
                if is_pending_owner_label(name):
                    task["owner_id"] = None
                    task.pop("owner_name", None)
                    continue
                owner_id = resolved.get(name)
                if owner_id:
                    task["owner_id"] = owner_id
                else:
                    questions.append(f"请确认任务「{task.get('task_name')}」负责人：{task['owner_name']}")
        data["project"] = project
        data["tasks"] = tasks
        data["open_questions"] = list(dict.fromkeys(questions))
        return data

    def get_project_plan_draft(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("draft_id"):
            return self._draft_result(
                self.drafts.get(str(args["draft_id"]), actor), "get_project_plan_draft"
            )
        return {
            "ok": True,
            "action": "get_project_plan_draft",
            "drafts": self.drafts.list_drafts(actor),
        }

    def _draft_result(self, draft: dict[str, Any], action: str) -> dict[str, Any]:
        review = draft.get("review") or {}
        return {
            "ok": True,
            "action": action,
            "draft_id": draft["id"],
            "title": draft["title"],
            "status": draft["status"],
            "revision": draft["revision"],
            "publishable": bool(review.get("publishable")),
            "blocking": review.get("blocking", []),
            "warnings": review.get("warnings", []),
            "project_id": draft.get("project_id"),
            "content": draft.get("content"),
            "next_step": (
                "已发布"
                if draft["status"] == "PUBLISHED"
                else "草案仍有阻塞项，补齐后再校验"
                if review.get("blocking")
                else "请用户在计划草案卡片上核对并点击发布；助手不能代替用户发布"
                if draft["status"] == "REVIEWED"
                else "补齐信息后调用 review_project_plan_draft 校验"
            ),
            "card": {
                "type": "plan_draft",
                "draft_id": draft["id"],
                "title": draft["title"],
                "status": draft["status"],
                "revision": draft["revision"],
                "project_id": draft.get("project_id"),
            },
        }

    # ----------------------------------------------------------- change flow

    def preview_change(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        data = SchedulePreviewInput.model_validate(self._schedule_args(args))
        preview = SchedulingService(self.db).preview(project.id, data, actor)
        return {
            "ok": True,
            "action": "preview_change",
            "project_id": project.id,
            "read_only": True,
            **self._preview_summary(preview),
            "snapshot_token": preview["snapshot_token"],
            "note": "这是只读模拟，计划未改变；要正式执行请生成变更方案并由用户确认。",
            "card": {
                "type": "schedule_preview",
                "project_id": project.id,
                "feasible": preview["candidate"]["feasible"],
                "changed_tasks": len(preview["changes"]),
            },
        }

    @staticmethod
    def _schedule_args(args: dict[str, Any]) -> dict[str, Any]:
        payload = {
            key: args[key]
            for key in ("as_of", "changes", "links", "selections", "project_target_date")
            if args.get(key) is not None
        }
        return payload

    @staticmethod
    def _preview_summary(preview: dict[str, Any]) -> dict[str, Any]:
        candidate = preview["candidate"]
        current = preview["current"]
        return {
            "feasible": candidate["feasible"],
            "conflicts": candidate["conflicts"],
            "current_finish_date": current.get("project_finish_date"),
            "forecast_finish_date": candidate.get("project_finish_date"),
            "forecast_delta_workdays": preview.get("forecast_delta_workdays"),
            "current_target_date": preview.get("current_target_date"),
            "proposed_target_date": preview.get("proposed_target_date"),
            "changed_tasks": preview["changes"][:MAX_ROWS],
            "changed_task_count": len(preview["changes"]),
            "branch_dispositions": preview.get("branch_dispositions", []),
            "critical_task_ids": [
                task["task_id"] for task in candidate.get("tasks", []) if task.get("is_critical")
            ][:MAX_ROWS],
        }

    def propose_change(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Create a change proposal and validate it. Never confirms or applies."""
        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        change = ChangeRequest.model_validate(
            {
                **self._schedule_args(args),
                "changes": args.get("changes") or [],
                "new_tasks": args.get("new_tasks") or [],
            }
        )
        body = ProposalCreate(
            reason=str(args.get("reason") or "").strip(),
            change=change,
            source=args.get("source"),
            idempotency_key=self._key(args),
        )
        created = self.proposals.create(project.id, body, actor)
        validated = self.proposals.validate(
            project.id,
            created["id"],
            ProposalRevision(expected_revision=created["revision"]),
            actor,
        )
        self.db.commit()
        return self._proposal_result(project, validated, "propose_change")

    def get_change_proposal(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        if not args.get("proposal_id"):
            return {
                "ok": True,
                "action": "get_change_proposal",
                "project_id": project.id,
                "proposals": self.proposals.list_proposals(project.id, actor),
            }
        row = self.proposals.get(project.id, str(args["proposal_id"]), actor)
        return self._proposal_result(project, record(row), "get_change_proposal")

    def execute_change_plan(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Apply a proposal only after the same user confirmed it in the UI."""
        from app.schemas.change_proposal import ProposalApply
        from app.services.exceptions import DomainValidationError

        project = self.project(
            project_id=args.get("project_id"), project_code=args.get("project_code")
        )
        proposal_id = str(args.get("proposal_id") or "")
        if not proposal_id:
            raise DomainValidationError("proposal_id is required")
        row = self.proposals.get(project.id, proposal_id, actor, write=True)
        if row.status != "CONFIRMED":
            raise DomainValidationError(
                "方案尚未由当前用户在页面确认（需要 status=CONFIRMED）；助手不能代为确认"
            )
        if row.confirmed_by != actor.id:
            raise DomainValidationError("必须由确认该方案的同一账号执行")
        body = ProposalApply(
            expected_revision=int(args["expected_revision"]),
            digest=str(args["digest"]),
            idempotency_key=str(args["idempotency_key"]),
        )
        applied = self.proposals.apply(project.id, proposal_id, body, actor)
        self.db.commit()
        return self._proposal_result(project, applied, "execute_change_plan")

    def _proposal_result(
        self, project: Project, row: dict[str, Any], action: str
    ) -> dict[str, Any]:
        diff = row.get("diff") or {}
        preview = row.get("preview") or {}
        tasks = diff.get("tasks") or []
        return {
            "ok": True,
            "action": action,
            "project_id": project.id,
            "proposal_id": row["id"],
            "status": row["status"],
            "revision": row["revision"],
            "reason": row["reason"],
            "feasible": bool(preview.get("candidate", {}).get("feasible")),
            "conflicts": preview.get("candidate", {}).get("conflicts", []),
            "task_change_count": len(tasks),
            "task_changes": [
                {
                    "task_id": item["task_id"],
                    "task_name": (item["after"] or {}).get("task_name"),
                    "is_new": item["before"] is None,
                    "before_due_date": (item["before"] or {}).get("due_date"),
                    "after_due_date": (item["after"] or {}).get("due_date"),
                }
                for item in tasks[:MAX_ROWS]
            ],
            "project_target_change": diff.get("project"),
            "route_changes": diff.get("selections", []),
            "notify_user_ids": [item["user_id"] for item in diff.get("notifications", [])],
            "notify_count": len(diff.get("notifications", [])),
            "forecast_finish_date": preview.get("candidate", {}).get("project_finish_date"),
            "next_step": (
                "请用户在变更方案卡片上核对完整差异并确认执行；"
                "助手不能代替用户确认或执行，也不能声称计划已更新。"
            ),
            "card": {
                "type": "change_proposal",
                "project_id": project.id,
                "proposal_id": row["id"],
                "status": row["status"],
                "revision": row["revision"],
                "reason": row["reason"],
            },
        }

    # ---------------------------------------------------------- notifications

    def get_notification_status(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("proposal_id"):
            proposal = self.db.get(ChangeProposal, str(args["proposal_id"]))
            if proposal is None:
                raise DomainValidationError("变更方案不存在")
            events = self.notifications.list_for_proposal(proposal.project_id, proposal.id, actor)
            return {
                "ok": True,
                "action": "get_notification_status",
                "proposal_id": proposal.id,
                "project_id": proposal.project_id,
                "summary": self.notifications.status_summary(proposal.id),
                "events": [self._event_brief(event) for event in events],
                "note": (
                    "SENT 只表示渠道已接受，不代表本人已读；ACKNOWLEDGED 才是用户在系统内确认。"
                ),
                "card": {
                    "type": "notification_status",
                    "proposal_id": proposal.id,
                    "project_id": proposal.project_id,
                },
            }
        events = self.notifications.list_for_user(
            actor, status=args.get("status"), limit=int(args.get("limit") or 20)
        )
        return {
            "ok": True,
            "action": "get_notification_status",
            "recipient_id": actor.id,
            "events": [self._event_brief(event) for event in events],
            "note": "这些是发送给你本人的计划变更通知，确认知悉请在通知页面操作。",
            "card": {"type": "notification_status", "recipient_id": actor.id},
        }

    @staticmethod
    def _event_brief(event: dict[str, Any]) -> dict[str, Any]:
        return {
            key: event[key]
            for key in (
                "id",
                "proposal_id",
                "project_code",
                "recipient_id",
                "recipient_name",
                "status",
                "channel",
                "simulated",
                "attempts",
                "delivery_uncertain",
                "sent_at",
                "acknowledged_at",
                "last_error",
            )
        }

    # --------------------------------------------------------- risk & advice

    def list_risk_events(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Tracked risks with evidence. Project optional — omit to scan all visible projects."""
        status = str(args.get("status") or "OPEN")
        event_type = args.get("event_type")
        limit = max(1, min(int(args.get("limit") or MAX_ROWS), 100))
        service = RiskEventService(self.db)
        clock = BusinessClock()

        has_project = args.get("project_id") is not None or bool(args.get("project_code"))
        if has_project:
            project = self.project(
                project_id=args.get("project_id"), project_code=args.get("project_code")
            )
            if not can_view_project(self.db, actor, project):
                raise PermissionDeniedError("你无权查看该项目")
            projects = [project]
        else:
            projects = ProjectService(self.db).list_projects(actor)

        events: list[dict[str, Any]] = []
        summaries: dict[str, Any] = {}
        for project in projects:
            items = service.list_for_project(project.id, actor, status=status)
            if event_type:
                items = [item for item in items if item.get("event_type") == event_type]
            for item in items:
                brief = self._risk_brief(item)
                brief["project_id"] = project.id
                brief["project_code"] = project.project_code
                events.append(brief)
            summaries[project.project_code] = open_risk_summary(self.db, project.id)

        events.sort(
            key=lambda item: (
                item.get("status") != "OPEN",
                item.get("level") != "DELAYED",
                item.get("id") or 0,
            )
        )
        truncated = len(events) > limit
        page = events[:limit]
        return {
            "ok": True,
            "action": "list_risk_events",
            "scope": "project" if has_project else "visible_projects",
            "project_id": projects[0].id if has_project and projects else None,
            "project_code": projects[0].project_code if has_project and projects else None,
            "project_count": len(projects),
            "summary": (
                summaries.get(projects[0].project_code, {})
                if has_project and projects
                else {
                    "total": sum(s.get("total", 0) for s in summaries.values()),
                    "by_project": summaries,
                }
            ),
            "events": page,
            "total": len(events),
            "coverage": {
                "returned": len(page),
                "total_matched": len(events),
                "truncated": truncated,
            },
            "business_timezone": clock.timezone,
            "queried_at": clock.now().isoformat(),
            "note": (
                "OVERDUE 是已发生的事实；FORECAST_DELAY 是按当前计划的预测，不改变已承诺的目标日期；"
                "MISSING_DATA 表示数据不足以判断，不等于没有风险。"
                "项目 risk_level / 任务 ai_status=ON_TRACK 不能替代本查询。"
            ),
            "card": (
                {"type": "risk_events", "project_id": projects[0].id}
                if has_project and projects
                else {"type": "risk_events", "scope": "visible_projects"}
            ),
        }

    @staticmethod
    def _risk_brief(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item[key]
            for key in (
                "id",
                "event_type",
                "level",
                "status",
                "title",
                "cause",
                "task_id",
                "issue_id",
                "owner_name",
                "impact_date",
                "impact_days",
                "first_seen_at",
                "last_seen_at",
            )
        }

    def get_issue_evidence(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """The bounded evidence set for one problem, with source ids to cite."""
        issue = self.db.get(Issue, int(args["issue_id"]))
        if issue is None or not can_view_issue(self.db, actor, issue):
            raise DomainValidationError("问题不存在或你无权查看")
        bundle = ProjectContextService(self.db).for_issue(issue).as_dict()
        return {
            "ok": True,
            "action": "get_issue_evidence",
            "issue_id": issue.id,
            **bundle,
            "note": (
                "这是按相关性选出的有限证据，不是项目全部数据；引用时带上 source_type#source_id。"
                "data_gaps 里的内容必须如实转述，不要用推测填补。"
            ),
        }

    def get_issue_advice(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Advice versions on one problem, including who adopted what."""
        issue = self.db.get(Issue, int(args["issue_id"]))
        if issue is None or not can_view_issue(self.db, actor, issue):
            raise DomainValidationError("问题不存在或你无权查看")
        records = AdviceService(self.db).list_for_issue(issue.id, actor)
        return {
            "ok": True,
            "action": "get_issue_advice",
            "issue_id": issue.id,
            "project_id": issue.project_id,
            "advice": [self._advice_brief(item) for item in records[:10]],
            "note": (
                "采纳、驳回和效果评价都由用户在建议卡片上操作，助手不能代为采纳，"
                "也不能声称建议已被接受。"
            ),
            "card": {"type": "advice", "issue_id": issue.id},
        }

    @staticmethod
    def _advice_brief(item: dict[str, Any]) -> dict[str, Any]:
        content = item.get("content") or {}
        return {
            "id": item["id"],
            "version": item["version"],
            "status": item["status"],
            "problem_summary": content.get("problem_summary"),
            "options": [
                {
                    "name": option.get("name"),
                    "time_impact_days": option.get("time_impact_days"),
                    "resource_impact": option.get("resource_impact"),
                }
                for option in (content.get("options") or [])
            ],
            "recommended_option": content.get("recommended_option"),
            "data_gaps": content.get("data_gaps") or [],
            "evidence_count": len(item.get("evidence") or []),
            "action_items": item.get("action_items") or [],
            "outcome": item.get("outcome"),
            "issue_resolved": item.get("issue_resolved"),
        }

    def request_issue_advice(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Queue evidence-based advice generation. Produces a record, not a decision."""
        from app.models.ai_run import AIRunType
        from app.services.ai_run import AIRunService

        issue = self.db.get(Issue, int(args["issue_id"]))
        if issue is None or not can_view_issue(self.db, actor, issue):
            raise DomainValidationError("问题不存在或你无权查看")
        if not can_request_issue_advice(actor, issue):
            raise PermissionDeniedError("你不能为该问题请求建议")
        run = AIRunService(self.db).create_queued(
            run_type=AIRunType.ISSUE_ADVICE,
            resource_type="issue",
            resource_id=issue.id,
            created_by=actor.id,
        )
        self.db.commit()
        try:
            from app.workers.tasks import enqueue_advise_issue

            enqueue_advise_issue(issue.id, actor_id=actor.id, run_id=run.id)
        except Exception:  # noqa: BLE001 — the run row records that it was asked for
            pass
        return {
            "ok": True,
            "action": "request_issue_advice",
            "issue_id": issue.id,
            "project_id": issue.project_id,
            "ai_run_id": run.id,
            "note": (
                "建议在后台生成，完成后会作为新版本记录在该问题下，需要用户采纳才会产生行动项。"
            ),
            "card": {"type": "advice", "issue_id": issue.id},
        }

    # -------------------------------------------------------------- progress

    def submit_progress(self, actor: User, args: dict[str, Any]) -> dict[str, Any]:
        """Store the report verbatim. A report is not an authorization to replan."""
        task = self.db.get(Task, int(args["task_id"]))
        if task is None or not can_view_task(self.db, actor, task):
            raise TaskNotFoundError
        project = task.project
        if project is None or not can_submit_progress(actor, task, project):
            raise PermissionDeniedError("你不能为该任务提交进度")
        content = str(args.get("content") or "").strip()
        if len(content) < 2:
            raise DomainValidationError("进度内容不能为空")
        progress = ProgressService(self.db).submit_progress(
            task.id,
            ProgressSubmit(
                content=content, mark_completed=bool(args.get("mark_completed") or False)
            ),
            actor=actor,
        )
        self.db.flush()
        from app.models.ai_run import AIRunType
        from app.services.ai_run import AIRunService

        run = AIRunService(self.db).create_queued(
            run_type=AIRunType.PROGRESS_ANALYSIS,
            resource_type="progress_update",
            resource_id=progress.id,
            created_by=actor.id,
        )
        self.db.commit()
        try:
            from app.workers.tasks import enqueue_analyze_progress

            enqueue_analyze_progress(progress.id, run_id=run.id)
        except Exception:  # noqa: BLE001 — the report is saved either way
            pass
        return {
            "ok": True,
            "action": "submit_progress",
            "progress_id": progress.id,
            "task_id": task.id,
            "task_name": task.task_name,
            "project_code": project.project_code,
            "raw_content": progress.raw_content,
            "marked_completed": bool(args.get("mark_completed") or False),
            "ai_run_id": run.id,
            "note": (
                "原文已保存，AI 分析在后台进行。若这次汇报意味着计划要改，"
                "需要另外生成变更方案并由有权限的用户确认，不能凭汇报直接改期。"
            ),
        }

    # ------------------------------------------------------------- utilities

    @staticmethod
    def _key(args: dict[str, Any]) -> str:
        supplied = str(args.get("idempotency_key") or "").strip()
        return supplied if len(supplied) >= 8 else f"agent-{uuid4()}"


__all__ = ["ManagementPlanningService"]
