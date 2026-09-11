"""Read-only data completeness and consistency checks.

Before a project can be scheduled, predicted or reported on honestly, its data
has to support the claim. This service finds the places where it does not, and
says which ones actually block a calculation versus which ones only make the
answer less useful. It never writes: fixing the data is a decision for whoever
owns the project.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning import BranchGroup, BranchOption, Milestone, PlanVersion, WorkCalendar
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskLink, TaskStatus
from app.models.user import User, UserStatus

#: Scheduling or forecasting cannot produce a trustworthy answer.
BLOCKING = "BLOCKING"
#: The answer is computable but incomplete or unverifiable.
WARNING = "WARNING"


@dataclass
class Finding:
    code: str
    severity: str
    title: str
    #: What a person should do about it, in concrete terms.
    remedy: str
    project_id: int
    project_code: str
    count: int = 0
    #: Affected row ids, capped so a broken project cannot produce a huge report.
    sample: list[Any] = field(default_factory=list)
    detail: str | None = None


MAX_SAMPLE = 20


class DataIntegrityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_all(self, *, include_closed: bool = False) -> list[Finding]:
        query = select(Project).order_by(Project.id)
        if not include_closed:
            query = query.where(
                Project.status.notin_([ProjectStatus.COMPLETED, ProjectStatus.CANCELLED])
            )
        findings: list[Finding] = []
        for project in self.db.scalars(query):
            findings.extend(self.check_project(project))
        return findings

    def check_project(self, project: Project) -> list[Finding]:
        tasks = list(
            self.db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id))
        )
        links = list(self.db.scalars(select(TaskLink).where(TaskLink.project_id == project.id)))
        findings: list[Finding] = []
        for check in (
            self._missing_planning_fields,
            self._impossible_dates,
            self._actual_date_gaps,
            self._broken_links,
            self._dependency_cycles,
            self._route_consistency,
            self._calendar,
            self._baseline,
            self._people,
            self._milestones,
        ):
            findings.extend(check(project, tasks, links))
        return findings

    # ------------------------------------------------------------- the plan

    def _finding(self, project: Project, **kwargs: Any) -> Finding:
        return Finding(project_id=project.id, project_code=project.project_code, **kwargs)

    def _missing_planning_fields(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        active = [task for task in tasks if task.is_execution_active]
        missing = [
            task.id
            for task in active
            if task.planned_duration_days is None or task.start_date is None
        ]
        findings = []
        if missing:
            findings.append(
                self._finding(
                    project,
                    code="TASK_MISSING_DURATION",
                    severity=BLOCKING,
                    title="执行中任务缺少计划工期或开始日期",
                    remedy=(
                        "在任务详情补齐 planned_duration_days 与 start_date；"
                        "补齐前这些任务的预测视为不确定"
                    ),
                    count=len(missing),
                    sample=missing[:MAX_SAMPLE],
                )
            )
        no_owner = [task.id for task in active if task.owner_id is None]
        if no_owner:
            findings.append(
                self._finding(
                    project,
                    code="TASK_WITHOUT_OWNER",
                    severity=WARNING,
                    title="执行中任务没有负责人",
                    remedy="指派负责人，否则催报和通知没有接收对象",
                    count=len(no_owner),
                    sample=no_owner[:MAX_SAMPLE],
                )
            )
        if project.target_date is None:
            findings.append(
                self._finding(
                    project,
                    code="PROJECT_WITHOUT_TARGET",
                    severity=WARNING,
                    title="项目没有目标日期",
                    remedy="设置目标日期，否则无法判断预测是否偏离承诺",
                    count=1,
                )
            )
        return findings

    def _impossible_dates(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        bad = [
            task.id
            for task in tasks
            if task.start_date is not None
            and task.due_date is not None
            and task.due_date < task.start_date
        ]
        if not bad:
            return []
        return [
            self._finding(
                project,
                code="TASK_DATES_INVERTED",
                severity=BLOCKING,
                title="任务截止日期早于开始日期",
                remedy="修正日期后重新预览；引擎会拒绝这种输入",
                count=len(bad),
                sample=bad[:MAX_SAMPLE],
            )
        ]

    def _actual_date_gaps(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        findings = []
        finished_without_date = [
            task.id
            for task in tasks
            if task.status == TaskStatus.COMPLETED and task.actual_finish_date is None
        ]
        if finished_without_date:
            findings.append(
                self._finding(
                    project,
                    code="COMPLETED_WITHOUT_ACTUAL",
                    severity=WARNING,
                    title="已完成任务没有实际完成日期",
                    remedy="补录实际完成日期；不要用计划截止日期顶替，那会污染基线对比",
                    count=len(finished_without_date),
                    sample=finished_without_date[:MAX_SAMPLE],
                )
            )
        started_without_date = [
            task.id
            for task in tasks
            if task.status == TaskStatus.IN_PROGRESS and task.actual_start_date is None
        ]
        if started_without_date:
            findings.append(
                self._finding(
                    project,
                    code="IN_PROGRESS_WITHOUT_ACTUAL_START",
                    severity=WARNING,
                    title="进行中任务没有实际开始日期",
                    remedy="补录实际开始日期，剩余工期预测才有基准",
                    count=len(started_without_date),
                    sample=started_without_date[:MAX_SAMPLE],
                )
            )
        inverted = [
            task.id
            for task in tasks
            if task.actual_start_date
            and task.actual_finish_date
            and task.actual_finish_date < task.actual_start_date
        ]
        if inverted:
            findings.append(
                self._finding(
                    project,
                    code="ACTUAL_DATES_INVERTED",
                    severity=BLOCKING,
                    title="实际完成日期早于实际开始日期",
                    remedy="核对执行记录并修正；这是事实类字段，不能靠计算推导",
                    count=len(inverted),
                    sample=inverted[:MAX_SAMPLE],
                )
            )
        return findings

    # ------------------------------------------------------------- the graph

    def _broken_links(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        ids = {task.id for task in tasks}
        findings = []
        dangling = [
            link.id for link in links if link.source_id not in ids or link.target_id not in ids
        ]
        if dangling:
            findings.append(
                self._finding(
                    project,
                    code="LINK_CROSS_PROJECT",
                    severity=BLOCKING,
                    title="依赖引用了本项目以外的任务",
                    remedy="删除或改接这些依赖；引擎会拒绝跨项目关系",
                    count=len(dangling),
                    sample=dangling[:MAX_SAMPLE],
                )
            )
        self_loops = [link.id for link in links if link.source_id == link.target_id]
        if self_loops:
            findings.append(
                self._finding(
                    project,
                    code="LINK_SELF_REFERENCE",
                    severity=BLOCKING,
                    title="任务依赖自身",
                    remedy="删除这些依赖",
                    count=len(self_loops),
                    sample=self_loops[:MAX_SAMPLE],
                )
            )
        return findings

    def _dependency_cycles(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        ids = {task.id for task in tasks}
        graph: dict[int, list[int]] = defaultdict(list)
        for link in links:
            if link.source_id in ids and link.target_id in ids:
                graph[link.source_id].append(link.target_id)

        colour: dict[int, int] = {}
        cycles: list[list[int]] = []

        def visit(node: int, path: list[int]) -> None:
            colour[node] = 1
            path.append(node)
            for nxt in graph.get(node, []):
                if colour.get(nxt, 0) == 0:
                    visit(nxt, path)
                elif colour.get(nxt) == 1 and len(cycles) < 5:
                    cycles.append([*path[path.index(nxt) :], nxt])
            path.pop()
            colour[node] = 2

        import sys

        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, len(ids) * 4 + 1000))
        try:
            for node in sorted(ids):
                if colour.get(node, 0) == 0:
                    visit(node, [])
        finally:
            sys.setrecursionlimit(limit)

        if not cycles:
            return []
        return [
            self._finding(
                project,
                code="DEPENDENCY_CYCLE",
                severity=BLOCKING,
                title="依赖图存在环",
                remedy="打断环路；有环时排期无法计算，任何预测完成日期都不成立",
                count=len(cycles),
                sample=[" → ".join(str(item) for item in cycle) for cycle in cycles],
            )
        ]

    def _route_consistency(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        groups = list(
            self.db.scalars(select(BranchGroup).where(BranchGroup.project_id == project.id))
        )
        if not groups:
            return []
        options = list(
            self.db.scalars(
                select(BranchOption).where(BranchOption.group_id.in_([g.id for g in groups]))
            )
        )
        by_group: dict[int, list[BranchOption]] = defaultdict(list)
        for option in options:
            by_group[option.group_id].append(option)

        findings = []
        multi = [
            group.id
            for group in groups
            if sum(1 for option in by_group[group.id] if option.is_selected) > 1
        ]
        if multi:
            findings.append(
                self._finding(
                    project,
                    code="ROUTE_MULTIPLE_SELECTED",
                    severity=BLOCKING,
                    title="路线组存在多个当前选项",
                    remedy="保留一个当前路线；引擎在这种数据上拒绝计算",
                    count=len(multi),
                    sample=multi[:MAX_SAMPLE],
                )
            )
        selected = {
            group.id: next((option.id for option in by_group[group.id] if option.is_selected), None)
            for group in groups
        }
        group_of = {option.id: option.group_id for option in options}
        mismatched = [
            task.id
            for task in tasks
            if task.branch_option_id in group_of
            and task.is_active_branch
            != (selected.get(group_of[task.branch_option_id]) == task.branch_option_id)
        ]
        if mismatched:
            findings.append(
                self._finding(
                    project,
                    code="ROUTE_FLAG_MISMATCH",
                    severity=BLOCKING,
                    title="任务的激活标记与路线选择不一致",
                    remedy="通过路线切换重新设置，不要直接改 is_active_branch",
                    count=len(mismatched),
                    sample=mismatched[:MAX_SAMPLE],
                )
            )
        orphan = [
            task.id
            for task in tasks
            if task.branch_option_id is not None and task.branch_option_id not in group_of
        ]
        if orphan:
            findings.append(
                self._finding(
                    project,
                    code="ROUTE_OPTION_MISSING",
                    severity=BLOCKING,
                    title="任务引用了不存在的路线选项",
                    remedy="重新挂接到本项目的路线选项，或清除该引用",
                    count=len(orphan),
                    sample=orphan[:MAX_SAMPLE],
                )
            )
        return findings

    # ------------------------------------------------------------ the rest

    def _calendar(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        findings = []
        calendar = self.db.get(WorkCalendar, project.id)
        if calendar is None:
            findings.append(
                self._finding(
                    project,
                    code="CALENDAR_MISSING",
                    severity=WARNING,
                    title="项目没有工作日历配置",
                    remedy="配置日历，否则按默认周一至周五计算，节假日不会被排除",
                    count=1,
                )
            )
        elif not calendar.weekdays:
            findings.append(
                self._finding(
                    project,
                    code="CALENDAR_NO_WORKDAYS",
                    severity=BLOCKING,
                    title="工作日历没有任何工作日",
                    remedy="至少配置一个工作日；否则任何工期都无法落到日期上",
                    count=1,
                )
            )
        foreign = [task.id for task in tasks if task.calendar_id not in (None, project.id)]
        if foreign:
            findings.append(
                self._finding(
                    project,
                    code="TASK_FOREIGN_CALENDAR",
                    severity=BLOCKING,
                    title="任务引用了其他项目的日历",
                    remedy="改为本项目日历",
                    count=len(foreign),
                    sample=foreign[:MAX_SAMPLE],
                )
            )
        return findings

    def _baseline(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        row = self.db.scalar(
            select(PlanVersion.id)
            .where(
                PlanVersion.project_id == project.id,
                PlanVersion.kind == "BASELINE",
            )
            .limit(1)
        )
        if row is not None:
            return []
        return [
            self._finding(
                project,
                code="BASELINE_MISSING",
                severity=WARNING,
                title="项目没有基准计划版本",
                remedy="在计划页面保存一次基准；没有基准就无法说明偏差是新出现的还是一直存在",
                count=1,
            )
        ]

    def _people(self, project: Project, tasks: list[Task], links: list[TaskLink]) -> list[Finding]:
        owner_ids = {task.owner_id for task in tasks if task.owner_id}
        owner_ids.add(project.owner_id)
        inactive = []
        for user_id in sorted(filter(None, owner_ids)):
            user = self.db.get(User, user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                inactive.append(user_id)
        if not inactive:
            return []
        return [
            self._finding(
                project,
                code="OWNER_INACTIVE",
                severity=BLOCKING,
                title="负责人账号已停用或不存在",
                remedy="改派负责人；变更执行前会重新校验人员有效性，停用账号会导致方案被拒绝",
                count=len(inactive),
                sample=inactive[:MAX_SAMPLE],
            )
        ]

    def _milestones(
        self, project: Project, tasks: list[Task], links: list[TaskLink]
    ) -> list[Finding]:
        rows = list(
            self.db.scalars(
                select(Milestone).where(
                    Milestone.project_id == project.id, Milestone.status == "PLANNED"
                )
            )
        )
        assigned = {task.milestone_id for task in tasks if task.milestone_id}
        findings = []
        empty = [row.id for row in rows if row.id not in assigned]
        if empty:
            findings.append(
                self._finding(
                    project,
                    code="MILESTONE_WITHOUT_TASKS",
                    severity=WARNING,
                    title="里程碑没有关联任何任务",
                    remedy="把任务挂到里程碑上，否则达成判断没有依据",
                    count=len(empty),
                    sample=empty[:MAX_SAMPLE],
                )
            )
        undated = [row.id for row in rows if row.target_date is None]
        if undated:
            findings.append(
                self._finding(
                    project,
                    code="MILESTONE_WITHOUT_DATE",
                    severity=WARNING,
                    title="里程碑没有目标日期",
                    remedy="补齐目标日期，否则不会参与超期检查",
                    count=len(undated),
                    sample=undated[:MAX_SAMPLE],
                )
            )
        return findings


def summarise(findings: list[Finding]) -> dict[str, Any]:
    blocking = [item for item in findings if item.severity == BLOCKING]
    return {
        "total": len(findings),
        "blocking": len(blocking),
        "warning": len(findings) - len(blocking),
        "projects_with_blocking": sorted({item.project_code for item in blocking}),
        "ready_for_scheduling": not blocking,
        "findings": [asdict(item) for item in findings],
    }


__all__ = ["BLOCKING", "WARNING", "DataIntegrityService", "Finding", "summarise"]
