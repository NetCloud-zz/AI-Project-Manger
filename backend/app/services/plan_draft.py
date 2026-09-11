"""Conversational project drafting and atomic publication.

A draft can be incomplete on purpose — conversation rarely produces every field
at once. ``review`` states exactly what still blocks publication, and
``publish`` either writes the whole project, tasks, dependencies, milestones and
baseline version in one transaction, or writes nothing.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import can_create_project
from app.models.plan_draft import PlanDraft
from app.models.project import Project
from app.models.task import TaskLink, TaskLinkType
from app.models.user import User, UserStatus
from app.schemas.plan_draft import (
    PlanDraftContent,
    PlanDraftCreate,
    PlanDraftPublish,
    PlanDraftRevision,
    PlanDraftUpdate,
)
from app.schemas.planning import MilestoneInput, PlanVersionInput
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services.audit import AuditService
from app.services.change_proposal import ProposalConflict, canonical, digest, utc_now
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.planning import PlanningService, record
from app.services.project import ProjectService
from app.services.task import TaskService

TERMINAL = {"PUBLISHED", "DISCARDED"}


class PlanDraftService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)
        self.planning = PlanningService(db)

    # ------------------------------------------------------------- lifecycle

    def _guard(self, actor: User) -> None:
        if not can_create_project(actor) or actor.status != UserStatus.ACTIVE:
            raise PermissionDeniedError("只有管理员或项目负责人可以起草立项计划")

    def _draft(self, draft_id: str, actor: User) -> PlanDraft:
        self._guard(actor)
        row = self.db.get(PlanDraft, draft_id)
        if row is None:
            raise DomainValidationError("计划草案不存在")
        if row.created_by != actor.id and not _is_admin(actor):
            raise PermissionDeniedError("只能查看自己创建的计划草案")
        return row

    def create(self, body: PlanDraftCreate, actor: User) -> dict[str, Any]:
        self._guard(actor)
        existing = self.db.scalar(
            select(PlanDraft).where(
                PlanDraft.created_by == actor.id, PlanDraft.create_key == body.idempotency_key
            )
        )
        if existing:
            return self.view(existing)
        row = PlanDraft(
            id=str(uuid4()),
            created_by=actor.id,
            title=body.title,
            status="DRAFT",
            revision=1,
            content=body.content.model_dump(mode="json"),
            create_key=body.idempotency_key,
        )
        self.db.add(row)
        self.db.flush()
        self._audit(row, actor, "create")
        return self.view(row)

    def update(self, draft_id: str, body: PlanDraftUpdate, actor: User) -> dict[str, Any]:
        row = self._draft(draft_id, actor)
        self._revision(row, body.expected_revision)
        if row.status in TERMINAL:
            raise ProposalConflict("已发布或已废弃的草案不能编辑")
        row.title = body.title
        row.content = body.content.model_dump(mode="json")
        row.revision += 1
        row.status = "DRAFT"
        row.review = None
        row.digest = None
        row.failure_reason = None
        self.db.flush()
        self._audit(row, actor, "update")
        return self.view(row)

    def discard(self, draft_id: str, body: PlanDraftRevision, actor: User) -> dict[str, Any]:
        row = self._draft(draft_id, actor)
        self._revision(row, body.expected_revision)
        if row.status == "PUBLISHED":
            raise ProposalConflict("已发布的草案不能废弃；请对项目创建变更方案")
        row.status = "DISCARDED"
        row.digest = None
        self.db.flush()
        self._audit(row, actor, "discard")
        return self.view(row)

    def get(self, draft_id: str, actor: User) -> dict[str, Any]:
        return self.view(self._draft(draft_id, actor))

    def list_drafts(self, actor: User) -> list[dict[str, Any]]:
        self._guard(actor)
        rows = self.db.scalars(
            select(PlanDraft)
            .where(PlanDraft.created_by == actor.id)
            .order_by(PlanDraft.created_at.desc())
            .limit(50)
        )
        return [
            {key: value for key, value in self.view(row).items() if key != "content"}
            for row in rows
        ]

    def _revision(self, row: PlanDraft, expected: int) -> None:
        if row.revision != expected:
            raise ProposalConflict("草案版本已变化，请重新读取后再操作")

    def _audit(self, row: PlanDraft, actor: User, action: str) -> None:
        self.audit.record(
            action=f"plan_draft.{action}",
            resource_type="plan_draft",
            resource_id=row.id,
            user_id=actor.id,
            new_value={
                "revision": row.revision,
                "status": row.status,
                "title": row.title,
                "project_id": row.project_id,
            },
        )

    def view(self, row: PlanDraft) -> dict[str, Any]:
        payload = record(row)
        payload["created_by_name"] = self.planning.user_name(row.created_by)
        return payload

    # ---------------------------------------------------------------- review

    def review(self, draft_id: str, body: PlanDraftRevision, actor: User) -> dict[str, Any]:
        row = self._draft(draft_id, actor)
        self._revision(row, body.expected_revision)
        if row.status in TERMINAL:
            raise ProposalConflict("已发布或已废弃的草案不能重新校验")
        content = PlanDraftContent.model_validate(row.content)
        result = self.inspect(content)
        row.review = canonical(result)
        row.status = "REVIEWED" if not result["blocking"] else "DRAFT"
        row.digest = (
            digest({"content": row.content, "revision": row.revision, "review": row.review})
            if row.status == "REVIEWED"
            else None
        )
        self.db.flush()
        self._audit(row, actor, "review")
        return self.view(row)

    def inspect(self, content: PlanDraftContent) -> dict[str, Any]:
        """Deterministic completeness and consistency check; never writes."""
        blocking: list[str] = []
        warnings: list[str] = []
        project = content.project

        if self.db.scalar(
            select(Project.id).where(Project.project_code == project.project_code.upper())
        ):
            blocking.append(f"项目编号 {project.project_code.upper()} 已存在")
        owner_ids = list(project.owner_ids or [])
        if project.owner_id is not None and project.owner_id not in owner_ids:
            owner_ids.insert(0, project.owner_id)
        if not owner_ids:
            blocking.append("项目负责人未确定")
        for user_id in {*owner_ids, *[t.owner_id for t in content.tasks if t.owner_id]}:
            user = self.db.get(User, user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                blocking.append(f"人员 #{user_id} 不存在或已停用")
        if project.start_date and project.target_date and project.start_date > project.target_date:
            blocking.append("项目开始日期晚于目标日期")
        if not content.tasks:
            blocking.append("计划中没有任务")

        task_ids = {task.client_id for task in content.tasks}
        milestone_ids = {item.client_id for item in content.milestones}
        for task in content.tasks:
            label = task.task_name
            if task.owner_id is None:
                blocking.append(f"任务「{label}」缺少负责人")
            if task.due_date is None and task.start_date is None:
                warnings.append(f"任务「{label}」未设起止日期，发布后可再补齐")
            if task.start_date and task.due_date and task.start_date > task.due_date:
                blocking.append(f"任务「{label}」开始日期晚于截止日期")
            if task.due_date and project.target_date and task.due_date > project.target_date:
                warnings.append(f"任务「{label}」截止日期晚于项目目标日期")
            if task.milestone_client_id is not None and task.milestone_client_id not in (
                milestone_ids
            ):
                blocking.append(f"任务「{label}」引用了不存在的里程碑")
            if task.planned_duration_days is None and task.estimate_basis is None:
                warnings.append(f"任务「{label}」没有工期或估算依据，发布后需补齐")

        for link in content.links:
            if link.source_client_id not in task_ids or link.target_client_id not in task_ids:
                blocking.append("依赖引用了草案中不存在的任务")
        if not blocking and _has_cycle(task_ids, content.links):
            blocking.append("依赖关系存在环")
        for item in content.milestones:
            if item.target_date and project.target_date and item.target_date > project.target_date:
                warnings.append(f"里程碑「{item.name}」晚于项目目标日期")
        if content.open_questions:
            blocking.append("仍有未回答的问题：" + "；".join(content.open_questions[:5]))

        return {
            "blocking": list(dict.fromkeys(blocking)),
            "warnings": list(dict.fromkeys(warnings)),
            "task_count": len(content.tasks),
            "link_count": len(content.links),
            "milestone_count": len(content.milestones),
            "assumptions": content.assumptions,
            "publishable": not blocking,
            "checked_at": utc_now().isoformat(),
        }

    # --------------------------------------------------------------- publish

    def publish(self, draft_id: str, body: PlanDraftPublish, actor: User) -> dict[str, Any]:
        row = self._draft(draft_id, actor)
        self._revision(row, body.expected_revision)
        if row.status == "PUBLISHED":
            if row.publish_key == body.idempotency_key and row.digest == body.digest:
                return self.view(row)
            raise ProposalConflict("该草案已发布，不能重复发布")
        if row.status != "REVIEWED" or not row.digest or row.digest != body.digest:
            raise ProposalConflict("只能发布已校验且差异未变化的草案")
        reused = select(PlanDraft.id).where(PlanDraft.publish_key == body.idempotency_key)
        if self.db.scalar(reused):
            raise ProposalConflict("发布幂等键已用于其他草案")
        content = PlanDraftContent.model_validate(row.content)
        recheck = self.inspect(content)
        if recheck["blocking"]:
            row.status = "DRAFT"
            row.digest = None
            row.review = canonical(recheck)
            self.db.flush()
            self._audit(row, actor, "stale")
            return self.view(row)
        try:
            with self.db.begin_nested():
                result = self._write(row, content, actor)
                row.status = "PUBLISHED"
                row.publish_key = body.idempotency_key
                row.published_by = actor.id
                row.published_at = utc_now()
                row.project_id = result["project_id"]
                row.result = result
                self.db.flush()
                self._audit(row, actor, "publish")
        except Exception as exc:  # noqa: BLE001 — a failed publish must leave no partial project
            row.status = "FAILED"
            row.failure_reason = f"发布事务失败，未创建任何数据：{exc}"[:2000]
            self.db.flush()
            self._audit(row, actor, "failed")
        return self.view(row)

    def _write(self, row: PlanDraft, content: PlanDraftContent, actor: User) -> dict[str, Any]:
        spec = content.project
        owner_ids = list(spec.owner_ids or [])
        primary = spec.owner_id if spec.owner_id is not None else owner_ids[0]
        if primary not in owner_ids:
            owner_ids.insert(0, primary)
        project = ProjectService(self.db).create_project(
            ProjectCreate(
                project_code=spec.project_code,
                project_name=spec.project_name,
                goal=spec.goal,
                owner_id=primary,
                owner_ids=owner_ids,
                start_date=spec.start_date,
                target_date=spec.target_date,
            ),
            actor=actor,
        )
        self.db.flush()

        milestone_map: dict[int, int] = {}
        for item in content.milestones:
            created = self.planning.put_milestone(
                project.id,
                MilestoneInput(
                    name=item.name,
                    target_date=item.target_date,
                    deliverable=item.deliverable,
                    acceptance_criteria=item.acceptance_criteria,
                ),
                actor,
            )
            milestone_map[item.client_id] = created["id"]

        task_map: dict[int, int] = {}
        tasks = TaskService(self.db)
        for draft_task in content.tasks:
            assert draft_task.owner_id is not None
            created_task = tasks.create_task(
                project.id,
                TaskCreate(
                    task_name=draft_task.task_name,
                    owner_id=draft_task.owner_id,
                    due_date=draft_task.due_date,
                    start_date=draft_task.start_date,
                    work_stream=draft_task.work_stream,
                    description=draft_task.description,
                    deliverable=draft_task.deliverable,
                    acceptance_criteria=draft_task.acceptance_criteria,
                    planned_duration_days=draft_task.planned_duration_days,
                    earliest_start_date=draft_task.earliest_start_date,
                    fixed_start_date=draft_task.fixed_start_date,
                    fixed_due_date=draft_task.fixed_due_date,
                    milestone_id=(
                        milestone_map.get(draft_task.milestone_client_id)
                        if draft_task.milestone_client_id is not None
                        else None
                    ),
                ),
                actor=actor,
            )
            task_map[draft_task.client_id] = created_task.id
        self.db.flush()

        for link in content.links:
            self.db.add(
                TaskLink(
                    project_id=project.id,
                    source_id=task_map[link.source_client_id],
                    target_id=task_map[link.target_client_id],
                    link_type=TaskLinkType(link.link_type),
                    lag_days=link.lag_days,
                )
            )
        self.db.flush()

        version = self.planning.capture_version(
            project.id,
            PlanVersionInput(
                reason=f"立项发布：{row.title}",
                expected_latest_version=0,
            ),
            actor,
        )
        self.audit.record(
            action="plan_draft.published",
            resource_type="project",
            resource_id=str(project.id),
            user_id=actor.id,
            new_value={
                "draft_id": row.id,
                "revision": row.revision,
                "task_id_map": task_map,
                "milestone_id_map": milestone_map,
                "plan_version_id": version["id"],
                "assumptions": content.assumptions,
            },
        )
        return {
            "project_id": project.id,
            "project_code": project.project_code,
            # String keys so the map reads the same before and after a JSON round trip.
            "task_id_map": {str(key): value for key, value in task_map.items()},
            "milestone_id_map": {str(key): value for key, value in milestone_map.items()},
            "link_count": len(content.links),
            "plan_version_id": version["id"],
        }


def _is_admin(actor: User) -> bool:
    from app.models.user import UserRole

    return actor.role == UserRole.ADMIN


def _has_cycle(task_ids: set[int], links: list[Any]) -> bool:
    degrees = dict.fromkeys(task_ids, 0)
    outgoing: dict[int, list[int]] = {key: [] for key in task_ids}
    for link in links:
        outgoing[link.source_client_id].append(link.target_client_id)
        degrees[link.target_client_id] += 1
    queue = [key for key, count in degrees.items() if count == 0]
    seen = 0
    while queue:
        node = queue.pop()
        seen += 1
        for target in outgoing[node]:
            degrees[target] -= 1
            if degrees[target] == 0:
                queue.append(target)
    return seen != len(task_ids)


__all__ = ["PlanDraftService"]
