"""Reviewed project changes. Caller commits; application writes live in a savepoint."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.change_proposal import ChangeProposal
from app.models.notification import PLAN_CHANGE, NotificationEvent
from app.models.planning import (
    BranchGroup,
    BranchOption,
    PlanVersion,
    ProjectMember,
    TaskParticipant,
    WorkCalendar,
)
from app.models.project import Project, project_owners
from app.models.task import Task, TaskLink, TaskLinkType, TaskStatus
from app.models.user import User, UserStatus
from app.schemas.change_proposal import (
    ChangeRequest,
    ProposalApply,
    ProposalConfirmation,
    ProposalCreate,
    ProposalEdit,
    ProposalRevision,
)
from app.schemas.planning import BranchSelectInput, PlanVersionInput
from app.schemas.scheduling import SchedulePreviewInput, ScheduleTaskPatch
from app.schemas.task import TaskPlanningFields, TaskUpdate
from app.services.audit import AuditService
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.planning import PlanningService, record
from app.services.risk_engine import RiskEngine
from app.services.scheduling import SchedulingService
from app.services.task import TaskService, _normalize_work_stream


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical(value: Any) -> Any:
    return jsonable_encoder(value)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            canonical(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class ProposalConflict(DomainValidationError):
    pass


EDITABLE = set(TaskPlanningFields.model_fields) | {
    "task_name",
    "owner_id",
    "work_stream",
    "start_date",
    "due_date",
}


class ChangeProposalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.planning = PlanningService(db)
        self.audit = AuditService(db)

    def scope(self, project_id: int, actor: User, *, write: bool = True) -> Project:
        project = self.planning.project(project_id, actor, write=write, full=True)
        if write:
            # Reads after waiting for a project lock must not reuse pre-lock ORM snapshots.
            self.db.expire_all()
            project = self.planning.project(project_id, actor, write=True, full=True)
            if actor.status != UserStatus.ACTIVE:
                raise PermissionDeniedError()
        return project

    def get(
        self, project_id: int, proposal_id: str, actor: User, *, write: bool = False
    ) -> ChangeProposal:
        self.scope(project_id, actor, write=write)
        row = self.db.get(ChangeProposal, proposal_id)
        if row is None or row.project_id != project_id:
            raise DomainValidationError("变更方案不存在于该项目")
        return row

    def list_proposals(self, project_id: int, actor: User) -> list[dict]:
        self.scope(project_id, actor, write=False)
        rows = self.db.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.project_id == project_id)
            .order_by(ChangeProposal.created_at.desc(), ChangeProposal.id)
            .limit(100)
        )
        return [
            {
                key: value
                for key, value in record(row).items()
                if key not in {"request", "preview", "diff"}
            }
            for row in rows
        ]

    def _revision(self, row: ChangeProposal, expected: int) -> None:
        if row.revision != expected:
            raise ProposalConflict("方案版本已变化，请重新查看完整差异")

    def _source(self, row: ChangeProposal) -> dict | None:
        if not row.source:
            return None
        from app.models.issue import Issue
        from app.models.progress_update import ProgressUpdate

        model: Any = Issue if row.source["kind"] == "ISSUE" else ProgressUpdate
        source = self.db.scalar(
            select(model)
            .where(model.id == row.source["id"])
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if source is None:
            raise DomainValidationError("方案来源不存在")
        task = self.db.get(Task, source.task_id) if not isinstance(source, Issue) else None
        if not isinstance(source, Issue) and task is None:
            raise DomainValidationError("来源关联的任务不存在")
        if isinstance(source, Issue):
            pid = source.project_id
        else:
            assert task is not None
            pid = task.project_id
        if pid != row.project_id:
            raise DomainValidationError("方案来源不属于本项目")
        return record(source)

    def create(self, project_id: int, body: ProposalCreate, actor: User) -> dict:
        self.scope(project_id, actor)
        create_hash = digest(body.model_dump(mode="json", exclude_unset=True))
        existing = self.db.scalar(
            select(ChangeProposal).where(
                ChangeProposal.project_id == project_id,
                ChangeProposal.created_by == actor.id,
                ChangeProposal.create_key == body.idempotency_key,
            )
        )
        if existing:
            if existing.create_hash != create_hash:
                raise ProposalConflict("该幂等键已用于不同的创建请求")
            return record(existing)
        row = ChangeProposal(
            id=str(uuid4()),
            project_id=project_id,
            created_by=actor.id,
            status="DRAFT",
            revision=1,
            reason=body.reason,
            request=body.change.model_dump(mode="json", exclude_unset=True),
            source=body.source.model_dump() if body.source else None,
            create_key=body.idempotency_key,
            create_hash=create_hash,
        )
        self._source(row)
        self.db.add(row)
        self.db.flush()
        self._audit(row, actor, "create")
        return record(row)

    def _audit(self, row: ChangeProposal, actor: User, action: str) -> None:
        self.audit.record(
            action=f"proposal.{action}",
            resource_type="change_proposal",
            resource_id=row.id,
            user_id=actor.id,
            new_value={
                "revision": row.revision,
                "status": row.status,
                "reason": row.reason,
                "digest": row.digest,
            },
        )

    def edit(self, project_id: int, proposal_id: str, body: ProposalEdit, actor: User) -> dict:
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        if row.status in {"APPLIED", "REJECTED"}:
            raise ProposalConflict("已执行或已拒绝方案不能编辑，请创建新方案")
        row.request = body.change.model_dump(mode="json", exclude_unset=True)
        row.reason = body.reason
        row.revision += 1
        row.status = "DRAFT"
        row.preview = row.diff = None
        row.digest = row.snapshot_token = None
        row.confirmed_by = row.confirmed_at = row.expires_at = None
        row.failure_reason = None
        self.db.flush()
        self._audit(row, actor, "edit")
        return record(row)

    def _latest(self, project_id: int) -> int:
        return (
            self.db.scalar(
                select(func.max(PlanVersion.version)).where(PlanVersion.project_id == project_id)
            )
            or 0
        )

    def _today(self, project_id: int) -> str:
        calendar = self.db.get(WorkCalendar, project_id)
        return (
            utc_now()
            .astimezone(ZoneInfo(calendar.timezone if calendar else "Asia/Shanghai"))
            .date()
            .isoformat()
        )

    def _fingerprint(self, row: ChangeProposal, base: dict) -> str:
        owners = list(
            self.db.execute(
                select(project_owners.c.user_id)
                .where(project_owners.c.project_id == row.project_id)
                .order_by(project_owners.c.user_id)
            ).scalars()
        )
        members = self.planning.rows(ProjectMember, row.project_id)
        participants = list(
            self.db.scalars(
                select(TaskParticipant)
                .join(Task, Task.id == TaskParticipant.task_id)
                .where(Task.project_id == row.project_id)
                .order_by(TaskParticipant.task_id, TaskParticipant.user_id)
            )
        )
        return digest(
            {
                "schedule": base["snapshot_token"],
                "owners": owners,
                "members": [record(m) for m in sorted(members, key=lambda m: m.user_id)],
                "participants": [record(p) for p in participants],
                "version": self._latest(row.project_id),
                "source": self._source(row),
            }
        )

    def _lock_users(self, row: ChangeProposal, actor: User) -> None:
        project = self.db.get(Project, row.project_id)
        assert project is not None
        change = ChangeRequest.model_validate(row.request)
        ids = {actor.id, project.owner_id} | {owner.id for owner in project.owners}
        ids.update(task.owner_id for task in self.planning.rows(Task, row.project_id) if task.owner_id)
        ids.update(member.user_id for member in self.planning.rows(ProjectMember, row.project_id))
        ids.update(p.owner_id for p in change.changes if p.owner_id is not None)
        ids.update(item.task.owner_id for item in change.new_tasks if item.task.owner_id is not None)
        ids.discard(None)
        # Acquire the complete set once in a stable order across projects.
        list(
            self.db.scalars(
                select(User)
                .where(User.id.in_(ids))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        self.planning.project(row.project_id, actor, write=True, full=True)
        if actor.status != UserStatus.ACTIVE:
            raise PermissionDeniedError()

    def _compute(self, row: ChangeProposal, actor: User) -> tuple[dict, dict, str]:
        self._lock_users(row, actor)
        change = ChangeRequest.model_validate(row.request)
        today = self._today(row.project_id)
        if change.as_of and change.as_of.isoformat() != today:
            raise DomainValidationError(
                "执行方案必须使用项目时区今天作为预测基准日；历史假设请使用只读预览"
            )
        base = SchedulingService(self.db).preview(
            row.project_id, SchedulePreviewInput(as_of=today), actor
        )
        if (
            change.expected_snapshot_token
            and change.expected_snapshot_token != base["snapshot_token"]
        ):
            raise ProposalConflict("原排期预览已过期，请重新计算")
        token = self._fingerprint(row, base)
        tasks = self.planning.rows(Task, row.project_id)
        original = {task.id: task for task in tasks}
        extras = []
        for new in change.new_tasks:
            TaskService(self.db)._validate_planning(row.project_id, new.task.model_dump())
            extras.append(
                Task(
                    id=new.client_id,
                    project_id=row.project_id,
                    **new.task.model_dump(),
                    is_active_branch=True,
                )
            )
        schedule_data = change.model_dump(
            mode="json",
            exclude_unset=True,
            exclude={"new_tasks", "expected_snapshot_token", "changes"},
        )
        schedule_data["as_of"] = today
        schedule_data["changes"] = [
            patch.model_dump(
                mode="json", exclude_unset=True, include=set(ScheduleTaskPatch.model_fields)
            )
            for patch in change.changes
        ]
        preview = SchedulingService(self.db).preview(
            row.project_id,
            SchedulePreviewInput.model_validate(schedule_data),
            actor,
            extra_tasks=extras,
        )
        preview["current"] = base["current"]
        final = {task.id: record(task) for task in [*tasks, *extras]}
        for extra in extras:
            final[extra.id]["work_stream"] = _normalize_work_stream(extra.work_stream)
        for patch in change.changes:
            if patch.task_id not in original:
                raise DomainValidationError("变更任务不属于本项目")
            if original[patch.task_id].status == TaskStatus.COMPLETED:
                raise DomainValidationError("已完成任务不能通过排期方案修改")
            values = patch.model_dump(mode="json", exclude_unset=True, exclude={"task_id"})
            if "task_name" in values and values.get("task_name") is None:
                raise DomainValidationError("任务名称不能为空")
            if "work_stream" in values:
                values["work_stream"] = _normalize_work_stream(values["work_stream"])
            final[patch.task_id].update(values)
        for computed in preview["candidate"]["tasks"]:
            target = final[computed["task_id"]]
            computed["task_name"] = target["task_name"]
            if computed["status"] == "COMPLETED":
                continue
            if computed["status"] == "TODO":
                target["start_date"] = computed["start_date"]
            target["due_date"] = computed["finish_date"]
        option_map = {
            option.id: option
            for option in self.db.scalars(
                select(BranchOption)
                .join(BranchGroup)
                .where(BranchGroup.project_id == row.project_id)
            )
        }
        for selection in change.selections:
            for task in tasks:
                option = option_map.get(task.branch_option_id)
                if option and option.group_id == selection.group_id:
                    active = option.id == selection.option_id
                    target = final[task.id]
                    target["is_active_branch"] = active
                    if (
                        not active
                        and task.is_active_branch
                        and task.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS)
                    ):
                        target["status"] = "CANCELLED"
                        target["branch_suspended_status"] = task.status.value
                    elif (
                        active
                        and task.status == TaskStatus.CANCELLED
                        and task.branch_suspended_status
                    ):
                        target["status"] = "IN_PROGRESS" if task.actual_start_date else "TODO"
                        target["branch_suspended_status"] = None
        owners = {
            item["owner_id"]
            for item in final.values()
            if item["status"] in ("TODO", "IN_PROGRESS") and item["is_active_branch"]
        } | {actor.id}
        owners.update(patch.owner_id for patch in change.changes if patch.owner_id is not None)
        users = list(
            self.db.scalars(
                select(User)
                .where(User.id.in_(owners))
                .order_by(User.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if {u.id for u in users if u.status == UserStatus.ACTIVE} != owners:
            raise DomainValidationError("执行任务的负责人不存在或已停用，请先调整人员")
        before_links = [
            {
                "source_id": link.source_id,
                "target_id": link.target_id,
                "link_type": link.link_type.value,
                "lag_days": link.lag_days,
            }
            for link in self.planning.rows(TaskLink, row.project_id)
        ]
        desired = (
            change.model_dump(mode="json")["links"] if change.links is not None else before_links
        )
        pairs = {(link["source_id"], link["target_id"]): dict(link) for link in desired}
        for link in preview["effective_links"]:
            pairs[(link["source_id"], link["target_id"])] = {
                key: link[key] for key in ("source_id", "target_id", "link_type", "lag_days")
            }
        after_links = [pairs[key] for key in sorted(pairs)]
        self._validate_graph(final, after_links)
        changed = []
        for task_id, target in sorted(final.items()):
            before = record(original[task_id]) if task_id in original else None
            target = canonical(target)
            if before is None or canonical(before) != target:
                changed.append({"task_id": task_id, "before": canonical(before), "after": target})
        project = self.db.get(Project, row.project_id)
        assert project is not None
        target_date = preview["proposed_target_date"]
        project_diff = (
            {"before": {"target_date": project.target_date}, "after": {"target_date": target_date}}
            if canonical(project.target_date) != canonical(target_date)
            else None
        )
        selections = [
            {
                "group_id": s.group_id,
                "before_option_id": next(
                    (
                        o.id
                        for o in option_map.values()
                        if o.group_id == s.group_id and o.is_selected
                    ),
                    None,
                ),
                "after_option_id": s.option_id,
            }
            for s in change.selections
        ]
        selections = [s for s in selections if s["before_option_id"] != s["after_option_id"]]
        diff = canonical(
            {
                "tasks": changed,
                "project": project_diff,
                "links": {
                    "before": sorted(
                        before_links, key=lambda link: (link["source_id"], link["target_id"])
                    ),
                    "after": after_links,
                },
                "selections": selections,
            }
        )
        diff["notifications"] = self._recipients(project, diff, final)
        if (
            not changed
            and not project_diff
            and not selections
            and diff["links"]["before"] == diff["links"]["after"]
        ):
            preview["candidate"]["feasible"] = False
            preview["candidate"]["conflicts"].append(
                {
                    "code": "NO_CHANGES",
                    "message": "没有需要执行的变更",
                    "task_ids": [],
                    "suggestion": "调整候选内容后重新验证",
                }
            )
        return canonical(preview), diff, token

    @staticmethod
    def _validate_graph(tasks: dict, links: list[dict]) -> None:
        degrees = dict.fromkeys(tasks, 0)
        outgoing: dict[int, list[int]] = {key: [] for key in tasks}
        for link in links:
            source, target = link["source_id"], link["target_id"]
            if source not in tasks or target not in tasks:
                raise DomainValidationError("依赖引用了其他项目或不存在的任务")
            outgoing[source].append(target)
            degrees[target] += 1
        queue = [key for key, count in degrees.items() if count == 0]
        seen = 0
        while queue:
            source = queue.pop()
            seen += 1
            for target in outgoing[source]:
                degrees[target] -= 1
                if degrees[target] == 0:
                    queue.append(target)
        if seen != len(tasks):
            raise DomainValidationError("完整依赖图存在环，不能保存")

    def _recipients(self, project: Project, diff: dict, final: dict) -> list[dict]:
        managers = {project.owner_id} | {owner.id for owner in project.owners}
        members = {m.user_id: m for m in self.planning.rows(ProjectMember, project.id)}
        participants = list(
            self.db.scalars(select(TaskParticipant).join(Task).where(Task.project_id == project.id))
        )
        affected = {t["task_id"] for t in diff["tasks"]}
        if diff["project"] or diff["links"]["before"] != diff["links"]["after"]:
            affected.update(final)
        ids = (
            managers
            | {final[tid]["owner_id"] for tid in affected}
            | {
                p.user_id
                for p in participants
                if p.task_id in affected and p.user_id in members and members[p.user_id].is_active
            }
        )
        users = self.db.scalars(
            select(User)
            .where(User.id.in_(ids))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        output = []
        for user in users:
            from app.core.permissions import can_view_full_project

            full = can_view_full_project(self.db, user, project)
            member = members.get(user.id)
            if user.status != UserStatus.ACTIVE or (member and not member.receive_notifications):
                continue
            visible = sorted(
                tid
                for tid in affected
                if full
                or final[tid]["owner_id"] == user.id
                or any(
                    p.task_id == tid and p.user_id == user.id and member and member.is_active
                    for p in participants
                )
            )
            if visible or full:
                # `full` decides whether project-wide facts may appear in the message.
                output.append({"user_id": user.id, "task_ids": visible, "full": full})
        return output

    def validate(
        self, project_id: int, proposal_id: str, body: ProposalRevision, actor: User
    ) -> dict:
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        if row.status not in {"DRAFT", "VALIDATED", "FAILED"}:
            raise ProposalConflict("请先编辑方案，清除旧确认后重新验证")
        preview, diff, token = self._compute(row, actor)
        row.request = {**row.request, "as_of": preview["as_of"]}
        row.preview = preview
        row.diff = diff
        row.snapshot_token = token
        row.base_plan_version = self._latest(project_id)
        row.status = "VALIDATED" if preview["candidate"]["feasible"] else "DRAFT"
        row.digest = (
            digest(
                {
                    "request": row.request,
                    "reason": row.reason,
                    "revision": row.revision,
                    "diff": diff,
                    "snapshot": token,
                }
            )
            if row.status == "VALIDATED"
            else None
        )
        row.expires_at = utc_now() + timedelta(hours=24)
        row.confirmed_by = row.confirmed_at = None
        row.failure_reason = None
        self.db.flush()
        self._audit(row, actor, "validate")
        return record(row)

    def _fresh(self, row: ChangeProposal, actor: User) -> bool:
        expiry = (
            row.expires_at.replace(tzinfo=UTC)
            if row.expires_at and row.expires_at.tzinfo is None
            else row.expires_at
        )
        if (
            not expiry
            or expiry <= utc_now()
            or row.request.get("as_of") != self._today(row.project_id)
        ):
            row.status = "EXPIRED"
            row.failure_reason = "预览已过期，请编辑并重新验证"
            self.db.flush()
            return False
        base = SchedulingService(self.db).preview(
            row.project_id, SchedulePreviewInput(as_of=row.request["as_of"]), actor
        )
        if self._fingerprint(row, base) != row.snapshot_token:
            row.status = "EXPIRED"
            row.failure_reason = "当前计划、来源或参与关系已变化，请重新预览"
            self.db.flush()
            return False
        return True

    def confirm(
        self, project_id: int, proposal_id: str, body: ProposalConfirmation, actor: User
    ) -> dict:
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        self._lock_users(row, actor)
        if row.status == "CONFIRMED" and row.confirmed_by == actor.id and row.digest == body.digest:
            self._fresh(row, actor)
            return record(row)
        if row.status != "VALIDATED" or row.digest != body.digest:
            raise ProposalConflict("只能确认当前已验证版本的完整差异")
        if not self._fresh(row, actor):
            return record(row)
        row.status = "CONFIRMED"
        row.confirmed_by = actor.id
        row.confirmed_at = utc_now()
        self.db.flush()
        self._audit(row, actor, "confirm")
        return record(row)

    def reject(
        self, project_id: int, proposal_id: str, body: ProposalRevision, actor: User
    ) -> dict:
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        if row.status == "APPLIED":
            raise ProposalConflict("已执行方案不能直接撤销；请创建反向变更并重新验证")
        row.status = "REJECTED"
        row.confirmed_by = row.confirmed_at = None
        self.db.flush()
        self._audit(row, actor, "reject")
        return record(row)

    def compensate(
        self, project_id: int, proposal_id: str, body: ProposalApply, actor: User
    ) -> dict:
        """Reverse only still-matching planned values; retain later changes and actual facts."""
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        if row.status != "APPLIED" or row.digest != body.digest:
            raise ProposalConflict("只能为已执行的当前方案生成补偿草案")
        assert row.diff is not None and row.result is not None
        changes = []
        retained = []
        for item in row.diff["tasks"]:
            if item["before"] is None:
                retained.append("新增任务保留，不自动删除或取消")
                continue
            task = self.db.get(Task, item["task_id"])
            if task is None or task.status == TaskStatus.COMPLETED:
                retained.append(f"任务 #{item['task_id']} 已完成或不存在，保留现状")
                continue
            current = canonical(record(task))
            patch = {}
            for key in sorted(EDITABLE - {"actual_start_date", "actual_finish_date"}):
                before, after = item["before"].get(key), item["after"].get(key)
                if before == after:
                    continue
                if current.get(key) != after or (key == "start_date" and task.actual_start_date):
                    retained.append(f"任务 #{task.id} 的 {key} 有后续变化，保留现状")
                else:
                    patch[key] = before
            if patch:
                changes.append({"task_id": task.id, **patch})

        def indexed(links: list[dict]) -> dict:
            return {(link["source_id"], link["target_id"]): link for link in links}

        before_links = indexed(row.diff["links"]["before"])
        mapping = row.result.get("task_id_map", {})
        after_links = indexed(
            [
                {
                    **link,
                    "source_id": mapping.get(str(link["source_id"]), link["source_id"]),
                    "target_id": mapping.get(str(link["target_id"]), link["target_id"]),
                }
                for link in row.diff["links"]["after"]
            ]
        )
        links = indexed(
            [
                {
                    "source_id": link.source_id,
                    "target_id": link.target_id,
                    "link_type": link.link_type.value,
                    "lag_days": link.lag_days,
                }
                for link in self.planning.rows(TaskLink, project_id)
            ]
        )
        for pair in sorted(before_links.keys() | after_links.keys()):
            if before_links.get(pair) == after_links.get(pair):
                continue
            if links.get(pair) != after_links.get(pair):
                retained.append(f"依赖 {pair} 有后续变化，保留现状")
            elif pair in before_links:
                links[pair] = before_links[pair]
            else:
                links.pop(pair, None)
        selections = []
        for selection in row.diff["selections"]:
            option = self.db.get(BranchOption, selection["after_option_id"])
            if option and option.is_selected and selection["before_option_id"] is not None:
                selections.append(
                    {"group_id": selection["group_id"], "option_id": selection["before_option_id"]}
                )
            else:
                retained.append("路线已有后续变化或无原选项，保留现状")
        change: dict[str, Any] = {
            "changes": changes,
            "links": list(links.values()),
            "selections": selections,
        }
        project = self.db.get(Project, project_id)
        assert project is not None
        project_diff = row.diff["project"]
        if project_diff:
            if canonical(project.target_date) == project_diff["after"]["target_date"]:
                change["project_target_date"] = project_diff["before"]["target_date"]
            else:
                retained.append("项目目标已有后续变化，保留现状")
        change["expected_snapshot_token"] = SchedulingService(self.db).preview(
            project_id, SchedulePreviewInput(as_of=self._today(project_id)), actor
        )["snapshot_token"]
        reason = f"补偿方案 {row.id}：恢复仍匹配的计划字段，须重新核对与计算。"
        if retained:
            reason += "未自动逆转：" + "；".join(dict.fromkeys(retained))
        result = self.create(
            project_id,
            ProposalCreate(
                reason=reason[:2000], change=change, idempotency_key=body.idempotency_key
            ),
            actor,
        )
        self._audit(row, actor, "compensate")
        return result

    def apply(self, project_id: int, proposal_id: str, body: ProposalApply, actor: User) -> dict:
        row = self.get(project_id, proposal_id, actor, write=True)
        self._revision(row, body.expected_revision)
        if row.status == "APPLIED":
            if (
                row.apply_key == body.idempotency_key
                and row.digest == body.digest
                and row.applied_by == actor.id
            ):
                return record(row)
            raise ProposalConflict("该方案已经执行，不能再次应用")
        if row.status != "CONFIRMED" or row.confirmed_by != actor.id or row.digest != body.digest:
            raise ProposalConflict("必须由确认该版本的当前账号执行")
        if self.db.scalar(
            select(ChangeProposal.id).where(ChangeProposal.apply_key == body.idempotency_key)
        ):
            raise ProposalConflict("执行幂等键已用于其他方案")
        self._lock_users(row, actor)
        if not self._fresh(row, actor):
            return record(row)
        preview, diff, token = self._compute(row, actor)
        if (
            not preview["candidate"]["feasible"]
            or token != row.snapshot_token
            or digest(diff) != digest(row.diff)
        ):
            row.status = "EXPIRED"
            row.failure_reason = "权限、人员或计算结果已变化，请重新验证和确认"
            self.db.flush()
            return record(row)
        try:
            with self.db.begin_nested():
                result = self._write(row, diff, actor)
                row.status = "APPLIED"
                row.apply_key = body.idempotency_key
                row.applied_by = actor.id
                row.applied_at = utc_now()
                row.applied_version_id = result["plan_version_id"]
                row.result = result
                self.db.flush()
                self._audit(row, actor, "apply")
        except Exception:
            # The savepoint contains every business/audit/version/outbox write.
            row.status = "FAILED"
            row.failure_reason = "执行事务失败；任务、计划版本和通知事件未提交。请重新验证。"
            self.db.flush()
            self._audit(row, actor, "failed")
        return record(row)

    def _write(self, row: ChangeProposal, diff: dict, actor: User) -> dict:
        pid = row.project_id
        if self._latest(pid) == 0:
            self.planning.capture_version(
                pid, PlanVersionInput(reason="变更前首次基准", expected_latest_version=0), actor
            )
        project = self.db.get(Project, pid)
        assert project is not None
        if diff["project"]:
            from datetime import date

            value = diff["project"]["after"]["target_date"]
            project.target_date = date.fromisoformat(value) if value else None
        change = ChangeRequest.model_validate(row.request)
        for selected in diff["selections"]:
            self.planning.select_branch(
                pid,
                selected["group_id"],
                BranchSelectInput(
                    option_id=selected["after_option_id"],
                    expected_selected_option_id=selected["before_option_id"],
                    reason=row.reason,
                ),
                actor,
            )
        id_map = {}
        affected = set()
        new_by_id = {item.client_id: item for item in change.new_tasks}
        for item in diff["tasks"]:
            task_id = item["task_id"]
            values = item["after"]
            if task_id < 0:
                new_data = new_by_id[task_id].task
                from app.schemas.task import TaskCreate

                data = TaskCreate.model_validate(
                    {
                        **new_data.model_dump(),
                        **{key: values[key] for key in EDITABLE if key in values},
                    }
                )
                task = TaskService(self.db).create_task(pid, data, actor=actor)
                id_map[task_id] = task.id
            else:
                existing_task = self.db.get(Task, task_id)
                assert existing_task is not None
                task = existing_task
                updates = {
                    key: values[key]
                    for key in EDITABLE
                    if values.get(key) != item["before"].get(key)
                }
                if updates:
                    validated = TaskUpdate.model_validate(updates).model_dump(exclude_unset=True)
                    merged = {
                        **{key: getattr(task, key) for key in TaskPlanningFields.model_fields},
                        "start_date": task.start_date,
                        "due_date": task.due_date,
                        "status": task.status,
                        **validated,
                    }
                    TaskService(self.db)._validate_planning(pid, merged)
                    for key, value in validated.items():
                        setattr(task, key, value)
            affected.add(task.id)
        self.db.flush()
        desired = {
            (
                id_map.get(link["source_id"], link["source_id"]),
                id_map.get(link["target_id"], link["target_id"]),
            ): link
            for link in diff["links"]["after"]
        }
        existing = {
            (link.source_id, link.target_id): link for link in self.planning.rows(TaskLink, pid)
        }
        for pair, link in existing.items():
            if pair not in desired:
                self.db.delete(link)
        self.db.flush()
        for pair, values in desired.items():
            link = existing.get(pair)
            if link is None:
                link = TaskLink(project_id=pid, source_id=pair[0], target_id=pair[1])
                self.db.add(link)
            link.link_type = TaskLinkType(values["link_type"])
            link.lag_days = values["lag_days"]
        self.db.flush()
        RiskEngine(self.db).refresh_project(pid, invalidate_task_ids=affected)
        self.db.flush()
        for task in self.planning.rows(Task, pid):
            self.db.expire(task, ["owner", "project"])
        version = self.planning.capture_version(
            pid,
            PlanVersionInput(reason=row.reason, expected_latest_version=self._latest(pid)),
            actor,
        )
        self.audit.record(
            action="project.change_apply",
            resource_type="project",
            resource_id=str(pid),
            user_id=actor.id,
            old_value={"proposal_id": row.id},
            new_value={
                "proposal_id": row.id,
                "revision": row.revision,
                "diff": diff,
                "task_id_map": id_map,
                "plan_version_id": version["id"],
            },
        )
        from app.notifications import get_notification_provider

        channel = get_notification_provider().name
        for recipient in diff["notifications"]:
            scoped_tasks = [
                item for item in diff["tasks"] if item["task_id"] in recipient["task_ids"]
            ]
            payload = {
                "proposal_id": row.id,
                "project_id": pid,
                "project_code": project.project_code,
                "project_name": project.project_name,
                "plan_version_id": version["id"],
                "reason": row.reason,
                "operator_id": actor.id,
                "operator_name": actor.name,
                # Project-wide facts only reach recipients allowed to see them.
                "project": diff["project"] if recipient.get("full") else None,
                "forecast_finish_date": (
                    (row.preview or {}).get("candidate", {}).get("project_finish_date")
                    if recipient.get("full")
                    else None
                ),
                "tasks": [
                    {
                        "task_id": id_map.get(item["task_id"], item["task_id"]),
                        "task_name": item["after"]["task_name"],
                        "is_new": item["before"] is None,
                        "before_start_date": (item["before"] or {}).get("start_date"),
                        "before_due_date": (item["before"] or {}).get("due_date"),
                        "start_date": item["after"]["start_date"],
                        "due_date": item["after"]["due_date"],
                        "status": item["after"]["status"],
                        "owner_id": item["after"]["owner_id"],
                    }
                    for item in scoped_tasks
                ],
            }
            self.db.add(
                NotificationEvent(
                    proposal_id=row.id,
                    project_id=pid,
                    recipient_id=recipient["user_id"],
                    event_type=PLAN_CHANGE,
                    dedupe_key=f"{PLAN_CHANGE}:{row.id}",
                    channel=channel,
                    payload=payload,
                    status="QUEUED",
                    attempts=0,
                    next_attempt_at=utc_now(),
                    delivery_uncertain=False,
                )
            )
        self.db.flush()
        return {
            "plan_version_id": version["id"],
            "task_id_map": id_map,
            "notification_events": len(diff["notifications"]),
        }
