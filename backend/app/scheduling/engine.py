"""Generalized-precedence scheduling over an acyclic graph; no ORM or writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from heapq import heappop, heappush
from typing import Literal

from app.scheduling.calendar import CalendarRangeError, WorkingCalendar

LINK_TYPES = {"FINISH_TO_START", "START_TO_START", "FINISH_TO_FINISH", "START_TO_FINISH"}


@dataclass(frozen=True)
class ScheduleTask:
    id: int
    project_id: int
    name: str
    status: str
    start_date: date | None
    due_date: date | None
    planned_duration_days: int | None = None
    remaining_duration_days: int | None = None
    actual_start_date: date | None = None
    actual_finish_date: date | None = None
    earliest_start_date: date | None = None
    fixed_start_date: date | None = None
    fixed_due_date: date | None = None
    requested_due_date: date | None = None
    active: bool = True
    milestone_id: int | None = None


@dataclass(frozen=True)
class ScheduleLink:
    source_id: int
    target_id: int
    link_type: str = "FINISH_TO_START"
    lag_days: int = 0
    synthetic: bool = False


@dataclass
class Diagnostic:
    code: str
    message: str
    task_ids: list[int] = field(default_factory=list)
    suggestion: str = "请补全资料或调整约束后重新预览"


@dataclass
class ScheduledTask:
    task_id: int
    task_name: str
    status: str
    start_date: date
    finish_date: date
    start_tick: int
    finish_tick: int
    remaining_duration_days: int | None
    actual_start_date: date | None = None
    actual_finish_date: date | None = None
    total_float_workdays: int | None = None
    network_float_workdays: int | None = None
    free_float_workdays: int | None = None
    critical: bool = False


@dataclass
class ScheduleResult:
    feasible: bool = True
    tasks: list[ScheduledTask] = field(default_factory=list)
    conflicts: list[Diagnostic] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    project_finish_date: date | None = None
    target_variance_workdays: int | None = None
    target_variance_calendar_days: int | None = None
    critical_task_ids: list[int] = field(default_factory=list)
    critical_links: list[ScheduleLink] = field(default_factory=list)
    critical_path: list[int] = field(default_factory=list)

    def error(
        self, code: str, message: str, ids: list[int] | None = None, suggestion: str | None = None
    ) -> None:
        self.feasible = False
        self.conflicts.append(
            Diagnostic(code, message, ids or [], suggestion or "请补全资料或调整约束后重新预览")
        )


def _weight(link: ScheduleLink, source_duration: int, target_duration: int) -> int:
    return (
        link.lag_days
        + {
            "FINISH_TO_START": source_duration,
            "START_TO_START": 0,
            "FINISH_TO_FINISH": source_duration - target_duration,
            "START_TO_FINISH": -target_duration,
        }[link.link_type]
    )


def schedule(
    tasks: list[ScheduleTask],
    links: list[ScheduleLink],
    calendar: WorkingCalendar,
    *,
    project_id: int,
    as_of: date,
    project_start: date | None = None,
    project_target: date | None = None,
    mode: Literal["preserve_dates", "earliest"] = "preserve_dates",
) -> ScheduleResult:
    result = ScheduleResult()
    tasks = sorted(tasks, key=lambda task: task.id)
    links = sorted(
        links, key=lambda link: (link.source_id, link.target_id, link.link_type, link.lag_days)
    )
    if len(tasks) > 1000 or len(links) > 5000:
        result.error("SIZE_LIMIT", "单次预览最多 1000 个任务、5000 条依赖")
        return result
    by_id = {task.id: task for task in tasks}
    if len(by_id) != len(tasks):
        result.error("DUPLICATE_TASK", "任务编号重复")
    for task in tasks:
        if task.project_id != project_id:
            result.error("CROSS_PROJECT_TASK", "任务属于其他项目", [task.id])
    pairs = set()
    for link in links:
        if link.source_id not in by_id or link.target_id not in by_id:
            result.error(
                "MISSING_REFERENCE", "依赖引用的任务不存在", [link.source_id, link.target_id]
            )
        if link.link_type not in LINK_TYPES or link.lag_days < 0:
            result.error("INVALID_LINK", "依赖类型或等待量无效", [link.source_id, link.target_id])
        if (link.source_id, link.target_id) in pairs:
            result.error(
                "DUPLICATE_LINK", "同一对任务只能有一条依赖", [link.source_id, link.target_id]
            )
        pairs.add((link.source_id, link.target_id))
    if not result.feasible:
        return result
    active = {task.id: task for task in tasks if task.active and task.status != "CANCELLED"}
    effective = []
    for link in links:
        if link.source_id in active and link.target_id in active:
            effective.append(link)
        elif link.target_id in active:
            # Branch filtering/rewiring is explicit in the adapter, never silently drop here.
            result.error(
                "INACTIVE_PREDECESSOR",
                "当前任务依赖已取消或未激活任务",
                [link.source_id, link.target_id],
            )
    incoming: dict[int, list[ScheduleLink]] = {task_id: [] for task_id in active}
    outgoing: dict[int, list[ScheduleLink]] = {task_id: [] for task_id in active}
    for link in effective:
        incoming[link.target_id].append(link)
        outgoing[link.source_id].append(link)
    degrees = {key: len(value) for key, value in incoming.items()}
    queue: list[int] = []
    for key, degree in degrees.items():
        if degree == 0:
            heappush(queue, key)
    order = []
    while queue:
        task_id = heappop(queue)
        order.append(task_id)
        for link in outgoing[task_id]:
            degrees[link.target_id] -= 1
            if degrees[link.target_id] == 0:
                heappush(queue, link.target_id)
    if len(order) != len(active):
        result.error(
            "DEPENDENCY_CYCLE",
            "有效任务依赖存在环",
            sorted(key for key, degree in degrees.items() if degree),
        )
    for task in active.values():
        if task.status == "TODO":
            if task.start_date is None or task.planned_duration_days is None:
                result.error(
                    "MISSING_PLAN_DATA",
                    "未开始任务须补全计划开始与工期，不能从日期差推测",
                    [task.id],
                )
            elif task.planned_duration_days < 1:
                result.error("INVALID_DURATION", "计划工期必须为正整数工作日", [task.id])
            if task.actual_start_date is not None or task.actual_finish_date is not None:
                result.error(
                    "TODO_HAS_ACTUAL_DATES",
                    "任务已有实际记录，请核对执行状态；不能按未开始任务移动",
                    [task.id],
                )
        elif task.status == "IN_PROGRESS":
            if task.actual_start_date is None or task.remaining_duration_days is None:
                result.error("MISSING_ACTUAL_DATA", "已开始任务须有实际开始及剩余工期", [task.id])
            elif task.actual_start_date > as_of or task.remaining_duration_days < 0:
                result.error(
                    "INVALID_ACTUAL_DATA", "实际开始晚于预测基准日，或剩余工期为负", [task.id]
                )
            if task.actual_finish_date is not None:
                result.error("STATUS_ACTUAL_CONFLICT", "未完成任务不能有实际完成日期", [task.id])
        elif task.status == "COMPLETED":
            if task.actual_start_date is None or task.actual_finish_date is None:
                result.error(
                    "MISSING_ACTUAL_DATA",
                    "已完成任务须补全实际起止日期，不能用计划日期替代",
                    [task.id],
                )
            elif (
                task.actual_finish_date < task.actual_start_date or task.actual_finish_date > as_of
            ):
                result.error(
                    "INVALID_ACTUAL_DATA", "实际日期倒置或实际完成晚于预测基准日", [task.id]
                )
        else:
            result.error("INVALID_STATUS", "不支持的任务状态", [task.id])
    if not result.feasible:
        return result
    computed: dict[int, ScheduledTask] = {}
    try:
        floor = max(calendar.start(as_of), calendar.start(project_start) if project_start else 0)
        for task_id in order:
            task = active[task_id]
            if task.status == "COMPLETED":
                assert task.actual_start_date is not None and task.actual_finish_date is not None
                start, finish = (
                    calendar.start(task.actual_start_date),
                    calendar.finish(task.actual_finish_date),
                )
                # Non-workday-only actual work has zero slots; real dates remain intact.
                finish = max(start, finish)
            elif task.status == "IN_PROGRESS":
                assert (
                    task.actual_start_date is not None and task.remaining_duration_days is not None
                )
                start = calendar.start(task.actual_start_date)
                finish = (
                    calendar.start(as_of) + task.remaining_duration_days
                    if task.remaining_duration_days
                    else calendar.finish(as_of)
                )
                finish = max(start, finish)
            else:
                assert task.start_date is not None and task.planned_duration_days is not None
                start = max(
                    floor, calendar.start(task.start_date) if mode == "preserve_dates" else floor
                )
                if task.earliest_start_date:
                    start = max(start, calendar.start(task.earliest_start_date))
                finish = start + task.planned_duration_days
            lower_start, lower_finish = start, finish
            for link in incoming[task_id]:
                previous = computed[link.source_id]
                bound = (
                    previous.finish_tick
                    if link.link_type in ("FINISH_TO_START", "FINISH_TO_FINISH")
                    else previous.start_tick
                ) + link.lag_days
                if link.link_type in ("FINISH_TO_START", "START_TO_START"):
                    lower_start = max(lower_start, bound)
                else:
                    lower_finish = max(lower_finish, bound)
            if task.status == "TODO":
                duration = finish - start
                start = max(lower_start, lower_finish - duration)
                finish = start + duration
                if (
                    task.fixed_due_date
                    and task.requested_due_date
                    and task.fixed_due_date != task.requested_due_date
                ):
                    result.error("FIXED_DATE_CONFLICT", "请求截止与固定截止冲突", [task_id])
                fixed_finish = task.requested_due_date or task.fixed_due_date
                for label, fixed_day in (
                    ("固定开始", task.fixed_start_date),
                    ("固定/请求截止", fixed_finish),
                ):
                    if fixed_day and not calendar.is_workday(fixed_day):
                        result.error(
                            "FIXED_NON_WORKDAY", f"{label}不是工作日，请核实预约或日历", [task_id]
                        )
                pinned_start = (
                    calendar.start(task.fixed_start_date) if task.fixed_start_date else None
                )
                if fixed_finish:
                    due_start = calendar.finish(fixed_finish) - duration
                    if pinned_start is not None and due_start != pinned_start:
                        result.error(
                            "FIXED_DURATION_CONFLICT",
                            "固定起止与工期不一致，不能压缩工期",
                            [task_id],
                        )
                    pinned_start = due_start if pinned_start is None else pinned_start
                if pinned_start is not None:
                    if pinned_start < start:
                        result.error(
                            "FIXED_DATE_CONFLICT",
                            "固定/请求日期早于依赖、基准日或最早开始允许时间",
                            [task_id],
                            "考虑改期、换路线或调整范围；系统不移动预约或压缩工期",
                        )
                    # Show the protected reservation even on infeasibility, never pretend it moved.
                    start, finish = pinned_start, pinned_start + duration
            else:
                if lower_start > start or (task.status == "COMPLETED" and lower_finish > finish):
                    result.error(
                        "ACTUAL_DEPENDENCY_CONFLICT",
                        "依赖要求移动实际日期，保留实际记录并报告冲突",
                        [task_id],
                    )
                if task.status == "IN_PROGRESS":
                    finish = max(finish, lower_finish)
                if (
                    task.earliest_start_date
                    and task.actual_start_date
                    and task.actual_start_date < task.earliest_start_date
                ):
                    result.error(
                        "ACTUAL_CONSTRAINT_CONFLICT", "实际开始早于最早开始约束", [task_id]
                    )
                if task.fixed_start_date and task.fixed_start_date != task.actual_start_date:
                    result.error("ACTUAL_CONSTRAINT_CONFLICT", "固定开始与实际开始冲突", [task_id])
                if (
                    task.fixed_due_date
                    and task.requested_due_date
                    and task.fixed_due_date != task.requested_due_date
                ):
                    result.error("FIXED_DATE_CONFLICT", "请求截止与固定截止冲突", [task_id])
                fixed_finish = task.requested_due_date or task.fixed_due_date
                if fixed_finish:
                    if task.status == "IN_PROGRESS" and not calendar.is_workday(fixed_finish):
                        result.error(
                            "FIXED_NON_WORKDAY", "固定/请求截止不是工作日，请核实日历", [task_id]
                        )
                    bound = calendar.finish(fixed_finish)
                    if task.status == "COMPLETED" and fixed_finish != task.actual_finish_date:
                        result.error(
                            "ACTUAL_CONSTRAINT_CONFLICT", "固定截止与实际完成冲突", [task_id]
                        )
                    elif task.status == "IN_PROGRESS":
                        if bound < finish:
                            result.error(
                                "FIXED_DATE_CONFLICT", "剩余工作或依赖无法满足固定截止", [task_id]
                            )
                        else:
                            finish = bound
            display_start = (
                task.actual_start_date if task.status != "TODO" else calendar.start_date(start)
            )
            display_finish = (
                task.actual_finish_date
                if task.status == "COMPLETED"
                else (
                    as_of
                    if task.status == "IN_PROGRESS"
                    and task.remaining_duration_days == 0
                    and finish == calendar.finish(as_of)
                    else calendar.finish_date(finish)
                )
            )
            assert display_start is not None and display_finish is not None
            computed[task_id] = ScheduledTask(
                task_id,
                task.name,
                task.status,
                display_start,
                display_finish,
                start,
                finish,
                task.remaining_duration_days,
                task.actual_start_date,
                task.actual_finish_date,
            )
        result.tasks = [computed[key] for key in sorted(computed)]
        if not computed:
            result.warnings.append(
                Diagnostic("NO_EXECUTION_TASKS", "没有当前路线的未取消任务，项目预测完成日期为空")
            )
            return result
        result.project_finish_date = max(item.finish_date for item in computed.values())
        if result.feasible:
            _floats(result, computed, active, outgoing, effective, order)
        if project_target:
            result.target_variance_workdays = calendar.delta(
                project_target, result.project_finish_date
            )
            result.target_variance_calendar_days = (
                result.project_finish_date - project_target
            ).days
            if result.project_finish_date > project_target:
                result.error(
                    "TARGET_DATE_EXCEEDED",
                    "预测完成超过项目目标；目标日期保持不变",
                    suggestion="考虑调整范围、依赖或路线后重算，或另行提出目标改期",
                )
    except CalendarRangeError as exc:
        result.error("CALENDAR_HORIZON", str(exc))
    return result


def _floats(
    result: ScheduleResult,
    computed: dict[int, ScheduledTask],
    tasks: dict[int, ScheduleTask],
    outgoing: dict[int, list[ScheduleLink]],
    links: list[ScheduleLink],
    order: list[int],
) -> None:
    horizon = max(item.finish_tick for item in computed.values())
    duration = {key: item.finish_tick - item.start_tick for key, item in computed.items()}
    network = {key: horizon - duration[key] for key in order}
    constrained = dict(network)
    for key in reversed(order):
        task = tasks[key]
        if (
            task.status != "TODO"
            or task.fixed_start_date
            or task.fixed_due_date
            or task.requested_due_date
        ):
            constrained[key] = min(constrained[key], computed[key].start_tick)
        for link in outgoing[key]:
            weight = _weight(link, duration[key], duration[link.target_id])
            network[key] = min(network[key], network[link.target_id] - weight)
            constrained[key] = min(constrained[key], constrained[link.target_id] - weight)
        item = computed[key]
        item.network_float_workdays = max(0, network[key] - item.start_tick)
        item.total_float_workdays = max(0, constrained[key] - item.start_tick)
        item.free_float_workdays = min(
            [horizon - item.finish_tick]
            + [
                computed[link.target_id].start_tick
                - item.start_tick
                - _weight(link, duration[key], duration[link.target_id])
                for link in outgoing[key]
            ]
        )
        item.critical = item.network_float_workdays == 0
    result.critical_task_ids = sorted(key for key, item in computed.items() if item.critical)
    result.critical_links = [
        link
        for link in links
        if computed[link.source_id].critical
        and computed[link.target_id].critical
        and computed[link.target_id].start_tick
        == computed[link.source_id].start_tick
        + _weight(link, duration[link.source_id], duration[link.target_id])
    ]
    paths: dict[int, list[int]] = {}
    for key in order:
        if not computed[key].critical:
            continue
        predecessors = [link.source_id for link in result.critical_links if link.target_id == key]
        prefix = max(
            (paths[source] for source in predecessors),
            key=lambda path: (len(path), tuple(-x for x in path)),
            default=[],
        )
        paths[key] = [*prefix, key]
    result.critical_path = max(
        (path for key, path in paths.items() if computed[key].finish_tick == horizon),
        key=lambda path: (len(path), tuple(-x for x in path)),
        default=[],
    )
