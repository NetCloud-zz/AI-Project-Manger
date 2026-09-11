"""Evidence selection for project-level analysis.

"Use all project data" is not the same as "put the database in the prompt".
This service picks a bounded, ranked set of records relevant to one question,
returns the source id and update time for each so the reader can go check it,
and states plainly what it did *not* look at. An analysis built on this can be
audited; one built on an unbounded dump cannot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.action_item import OPEN_ACTION_ITEM_STATUSES, ActionItem
from app.models.issue import OPEN_ISSUE_STATUSES, Issue
from app.models.planning import Milestone, PlanVersion
from app.models.progress_update import ProgressUpdate
from app.models.project import Project
from app.models.risk_event import RiskEvent, RiskEventLevel, RiskEventStatus
from app.models.task import Task, TaskLink
from app.models.user import User

#: Hard caps. Evidence is selected, never streamed wholesale.
MAX_PROGRESS_FOCUS = 8
MAX_PROGRESS_NEIGHBOUR = 4
MAX_NEIGHBOUR_TASKS = 12
MAX_ISSUES = 10
MAX_RISKS = 10
MAX_ACTIONS = 10
MAX_DETAIL_CHARS = 400

_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _clip(text: str | None) -> str:
    return (text or "").strip()[:MAX_DETAIL_CHARS]


def _issue_scope(issue: Issue, by_id: dict[int, Task]) -> str:
    task = by_id.get(issue.task_id) if issue.task_id else None
    return f"任务 {task.task_name}" if task else "项目级"


@dataclass(slots=True)
class Evidence:
    source_type: str
    source_id: int | None
    updated_at: str | None
    title: str
    detail: str
    #: Why this record was selected, so a reviewer can challenge the selection.
    relevance: str


@dataclass(slots=True)
class ContextBundle:
    project_id: int
    project_code: str
    focus: dict[str, Any]
    evidence: list[Evidence] = field(default_factory=list)
    #: What was searched, what was included, and what was deliberately left out.
    coverage: dict[str, Any] = field(default_factory=dict)
    #: Facts the analysis needs but the database does not have.
    data_gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_code": self.project_code,
            "focus": self.focus,
            "evidence": [asdict(item) for item in self.evidence],
            "coverage": self.coverage,
            "data_gaps": self.data_gaps,
        }

    def lines(self) -> list[str]:
        """Citable one-liners for a prompt: every claim keeps its source id."""
        return [
            f"[{item.source_type}#{item.source_id or '-'} @{item.updated_at or '未知'}] "
            f"{item.title}｜{item.detail}"
            for item in self.evidence
        ]


class ProjectContextService:
    """Builds a bounded evidence set around one issue or one project."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ----------------------------------------------------------------- entry

    def for_issue(self, issue: Issue) -> ContextBundle:
        project = issue.project
        task = issue.task
        bundle = ContextBundle(
            project_id=project.id,
            project_code=project.project_code,
            focus={
                "kind": "issue",
                "issue_id": issue.id,
                "title": issue.title,
                "severity": issue.severity.value,
                "status": issue.status.value,
                "task_id": task.id if task else None,
                "task_name": task.task_name if task else None,
                "project_goal": project.goal,
                "project_target_date": _iso(project.target_date),
            },
        )
        tasks = list(
            self.db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id))
        )
        by_id = {row.id: row for row in tasks}
        neighbours = self._neighbours(project.id, task, by_id) if task else []

        if task is not None:
            bundle.evidence.append(self._task(task, "问题直接关联的任务"))
            bundle.evidence.extend(self._progress(task, MAX_PROGRESS_FOCUS, "该任务的进展原文"))
        for neighbour, reason in neighbours[:MAX_NEIGHBOUR_TASKS]:
            bundle.evidence.append(self._task(neighbour, reason))
        for neighbour, _ in neighbours[:3]:
            bundle.evidence.extend(
                self._progress(neighbour, MAX_PROGRESS_NEIGHBOUR, "相邻任务的近期进展")
            )

        bundle.evidence.extend(self._other_issues(project.id, issue, by_id))
        bundle.evidence.extend(self._risks(project.id))
        bundle.evidence.extend(self._actions(project.id, issue))
        bundle.evidence.extend(self._milestones(project.id, task))
        bundle.evidence.extend(self._baseline(project.id))

        bundle.coverage = self._coverage(project, tasks, bundle, neighbours=len(neighbours))
        bundle.data_gaps = self._gaps(project, tasks, task)
        return bundle

    # ------------------------------------------------------------- selectors

    def _neighbours(
        self, project_id: int, task: Task, by_id: dict[int, Task]
    ) -> list[tuple[Task, str]]:
        """One hop along the dependency graph, in both directions."""
        links = self.db.scalars(select(TaskLink).where(TaskLink.project_id == project_id))
        found: dict[int, str] = {}
        for link in links:
            if link.target_id == task.id and link.source_id in by_id:
                found.setdefault(link.source_id, "该任务的前置任务，可能是问题来源")
            elif link.source_id == task.id and link.target_id in by_id:
                found.setdefault(link.target_id, "该任务的后续任务，会受这个问题影响")
        return [(by_id[task_id], reason) for task_id, reason in sorted(found.items())]

    def _task(self, task: Task, relevance: str) -> Evidence:
        remaining = task.remaining_duration_days
        return Evidence(
            source_type="task",
            source_id=task.id,
            updated_at=_iso(task.updated_at),
            title=task.task_name,
            detail=(
                f"状态 {task.status.value}｜计划 {_iso(task.start_date) or '未定'} ~ "
                f"{_iso(task.due_date)}｜工期 {task.planned_duration_days or '未知'} 工作日"
                f"｜剩余 {'未知' if remaining is None else remaining}"
                f"｜风险信号 {task.ai_status.value if task.ai_status else '无'}"
            ),
            relevance=relevance,
        )

    def _progress(self, task: Task, limit: int, relevance: str) -> list[Evidence]:
        rows = self.db.scalars(
            select(ProgressUpdate)
            .where(ProgressUpdate.task_id == task.id)
            .order_by(ProgressUpdate.created_at.desc(), ProgressUpdate.id.desc())
            .limit(limit)
        )
        return [
            Evidence(
                source_type="progress",
                source_id=row.id,
                updated_at=_iso(row.created_at),
                title=f"{task.task_name} 的进展汇报",
                detail=_clip(row.raw_content),
                relevance=relevance,
            )
            for row in rows
        ]

    def _other_issues(
        self, project_id: int, issue: Issue, by_id: dict[int, Task]
    ) -> list[Evidence]:
        candidates = self.db.scalars(
            select(Issue).where(
                Issue.project_id == project_id,
                Issue.id != issue.id,
                Issue.status.in_(OPEN_ISSUE_STATUSES),
            )
        )
        # Severity is stored as text, so rank it here rather than in SQL.
        rows = sorted(
            candidates,
            key=lambda row: (-_SEVERITY_RANK.get(row.severity.value, 0), -row.id),
        )[:MAX_ISSUES]
        return [
            Evidence(
                source_type="issue",
                source_id=row.id,
                updated_at=_iso(row.updated_at),
                title=row.title,
                detail=(
                    f"{row.severity.value}｜{row.status.value}｜"
                    f"{_issue_scope(row, by_id)}"
                    f"｜{_clip(row.description)}"
                ),
                relevance="本项目其他未解决问题，可能同源或叠加影响",
            )
            for row in rows
        ]

    def _risks(self, project_id: int) -> list[Evidence]:
        candidates = self.db.scalars(
            select(RiskEvent).where(
                RiskEvent.project_id == project_id,
                RiskEvent.status == RiskEventStatus.OPEN,
            )
        )
        rows = sorted(candidates, key=lambda row: (row.level != RiskEventLevel.DELAYED, row.id))[
            :MAX_RISKS
        ]
        return [
            Evidence(
                source_type="risk_event",
                source_id=row.id,
                updated_at=_iso(row.last_seen_at),
                title=row.title,
                detail=f"{row.event_type.value}｜{row.level.value}｜{_clip(row.cause)}",
                relevance="当前未关闭的风险记录",
            )
            for row in rows
        ]

    def _actions(self, project_id: int, issue: Issue) -> list[Evidence]:
        candidates = self.db.scalars(
            select(ActionItem).where(
                ActionItem.project_id == project_id,
                ActionItem.status.in_(OPEN_ACTION_ITEM_STATUSES),
            )
        )
        # Actions already attached to this issue matter most.
        rows = sorted(candidates, key=lambda row: (row.issue_id != issue.id, row.id))[:MAX_ACTIONS]
        return [
            Evidence(
                source_type="action_item",
                source_id=row.id,
                updated_at=_iso(row.updated_at),
                title=row.title,
                detail=(
                    f"{row.status.value}｜{row.priority.value}｜"
                    f"截止 {_iso(row.due_date) or '未定'}｜"
                    f"{'本问题的行动项' if row.issue_id == issue.id else '项目其他行动项'}"
                ),
                relevance="已经在跟踪的行动，避免重复建议",
            )
            for row in rows
        ]

    def _milestones(self, project_id: int, task: Task | None) -> list[Evidence]:
        query = select(Milestone).where(
            Milestone.project_id == project_id, Milestone.status == "PLANNED"
        )
        if task is not None and task.milestone_id is not None:
            query = query.where(Milestone.id == task.milestone_id)
        rows = self.db.scalars(query.order_by(Milestone.target_date).limit(5))
        return [
            Evidence(
                source_type="milestone",
                source_id=row.id,
                updated_at=_iso(row.updated_at),
                title=row.name,
                detail=f"目标日期 {_iso(row.target_date) or '未定'}｜{_clip(row.deliverable)}",
                relevance="受影响的交付节点",
            )
            for row in rows
        ]

    def _baseline(self, project_id: int) -> list[Evidence]:
        row = self.db.scalar(
            select(PlanVersion)
            .where(
                PlanVersion.project_id == project_id,
                PlanVersion.kind.in_(["BASELINE", "MIGRATION_BASELINE"]),
            )
            .order_by(PlanVersion.version)
            .limit(1)
        )
        if row is None:
            return []
        label = "首次基准" if row.kind == "BASELINE" else "迁移基准（非原始立项计划）"
        return [
            Evidence(
                source_type="plan_version",
                source_id=row.id,
                updated_at=_iso(row.created_at),
                title=f"计划{label} v{row.version}",
                detail=_clip(row.reason),
                relevance="对比基准，用于判断偏差是新增的还是长期存在的",
            )
        ]

    # -------------------------------------------------------------- coverage

    def _coverage(
        self,
        project: Project,
        tasks: list[Task],
        bundle: ContextBundle,
        *,
        neighbours: int,
    ) -> dict[str, Any]:
        counted: dict[str, int] = {}
        for item in bundle.evidence:
            counted[item.source_type] = counted.get(item.source_type, 0) + 1
        active = [task for task in tasks if task.is_execution_active]
        return {
            "project_tasks_total": len(tasks),
            "execution_active_tasks": len(active),
            "dependency_neighbours_found": neighbours,
            "included": counted,
            "limits": {
                "progress_per_focus_task": MAX_PROGRESS_FOCUS,
                "progress_per_neighbour_task": MAX_PROGRESS_NEIGHBOUR,
                "neighbour_tasks": MAX_NEIGHBOUR_TASKS,
                "issues": MAX_ISSUES,
                "risk_events": MAX_RISKS,
                "action_items": MAX_ACTIONS,
            },
            "excluded": [
                "未选中的备用路线任务不参与执行判断",
                "与该问题无依赖关系且无未解决问题的任务未纳入",
                "已解决的问题与已关闭的风险记录未纳入",
                "附件与外部文档不在本期范围内",
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _gaps(self, project: Project, tasks: list[Task], focus: Task | None) -> list[str]:
        gaps: list[str] = []
        active = [task for task in tasks if task.is_execution_active]
        missing_plan = [
            t for t in active if t.planned_duration_days is None or t.start_date is None
        ]
        if missing_plan:
            gaps.append(
                f"{len(missing_plan)} 个执行中任务缺少工期或开始日期，时间影响估算只能是粗略区间"
            )
        if project.target_date is None:
            gaps.append("项目没有目标日期，无法判断是否偏离承诺")
        if focus is not None:
            has_progress = self.db.scalar(
                select(ProgressUpdate.id).where(ProgressUpdate.task_id == focus.id).limit(1)
            )
            if has_progress is None:
                gaps.append(f"任务「{focus.task_name}」没有任何进展记录，只能依据计划字段判断")
        if focus is None:
            gaps.append("该问题没有关联任务，无法从任务进展中取证")
        if not self.db.scalar(
            select(PlanVersion.id).where(PlanVersion.project_id == project.id).limit(1)
        ):
            gaps.append("项目还没有保存任何计划版本，缺少对比基准")
        return gaps

    # ---------------------------------------------------------------- people

    def participant_names(self, project_id: int) -> list[str]:
        rows = self.db.scalars(
            select(User)
            .join(Task, Task.owner_id == User.id)
            .where(Task.project_id == project_id)
            .distinct()
            .limit(30)
        )
        return sorted({row.name for row in rows})


__all__ = ["ContextBundle", "Evidence", "ProjectContextService"]
