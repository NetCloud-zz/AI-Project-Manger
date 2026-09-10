"""Adapt an authorized project snapshot to the pure S2 engine without changing ORM state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.planning import BranchGroup, BranchOption, Milestone, PlanVersion, WorkCalendar
from app.models.task import Task, TaskLink
from app.models.user import User
from app.scheduling.calendar import WorkingCalendar
from app.scheduling.engine import Diagnostic, ScheduleLink, ScheduleResult, ScheduleTask, schedule
from app.schemas.scheduling import SchedulePreviewInput
from app.services.exceptions import DomainValidationError
from app.services.planning import PlanningService, record


class StaleSchedulePreview(DomainValidationError):
    def __init__(self) -> None:
        super().__init__("项目计划已变化，请重新获取预览")


class SchedulingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def preview(
        self,
        project_id: int,
        data: SchedulePreviewInput,
        actor: User,
        *,
        extra_tasks: list[Task] | None = None,
    ) -> dict[str, Any]:
        planning = PlanningService(self.db)
        project = planning.project(project_id, actor, full=True)
        tasks = [*planning.rows(Task, project_id), *(extra_tasks or [])]
        links = planning.rows(TaskLink, project_id)
        groups = planning.rows(BranchGroup, project_id)
        options = (
            list(
                self.db.scalars(
                    select(BranchOption).where(BranchOption.group_id.in_([g.id for g in groups]))
                )
            )
            if groups
            else []
        )
        milestones = planning.rows(Milestone, project_id)
        calendar_row = self.db.get(WorkCalendar, project_id)
        calendar_data: dict[str, Any] = (
            record(calendar_row)
            if calendar_row
            else {
                "weekdays": [0, 1, 2, 3, 4],
                "exceptions": {},
                "timezone": "Asia/Shanghai",
                "version": 0,
            }
        )
        source: dict[str, Any] = {
            "project": record(project),
            "tasks": [record(t) for t in tasks],
            "links": [record(link) for link in links],
            "calendar": calendar_data,
            "groups": [record(g) for g in groups],
            "options": [record(o) for o in options],
            "milestones": [record(m) for m in milestones],
        }
        # Canonical input fingerprint, not authorization to apply a future proposal.
        for key in ("tasks", "links", "groups", "options", "milestones"):
            source[key] = sorted(source[key], key=lambda row: row["id"])
        token = hashlib.sha256(
            json.dumps(source, sort_keys=True, default=str, ensure_ascii=False).encode()
        ).hexdigest()
        if data.expected_snapshot_token and data.expected_snapshot_token != token:
            raise StaleSchedulePreview()
        as_of = data.as_of or datetime.now(ZoneInfo(calendar_data["timezone"])).date()
        if len(tasks) > 1000 or len(links) > 5000:
            raise DomainValidationError("单次预览最多 1000 个任务、5000 条依赖")
        dates = [as_of]
        for row in [
            source["project"],
            *source["tasks"],
            *source["milestones"],
            *[change.model_dump(mode="json") for change in data.changes],
        ]:
            for key, value in row.items():
                if (key.endswith("_date") or key == "as_of") and value:
                    dates.append(date.fromisoformat(str(value)))
        if data.project_target_date:
            dates.append(data.project_target_date)
        try:
            calendar = WorkingCalendar(
                min(dates), calendar_data["weekdays"], calendar_data["exceptions"]
            )
            calendar.start(max(dates))
        except (ValueError, OverflowError) as exc:
            raise DomainValidationError(f"工作日历无法计算：{exc}") from exc
        if any(task.calendar_id not in (None, project_id) for task in tasks):
            raise DomainValidationError("任务不能引用其他项目的日历")
        current_tasks = [
            ScheduleTask(
                id=t.id,
                project_id=t.project_id,
                name=t.task_name,
                status=t.status.value,
                start_date=t.start_date,
                due_date=t.due_date,
                planned_duration_days=t.planned_duration_days,
                remaining_duration_days=t.remaining_duration_days,
                actual_start_date=t.actual_start_date,
                actual_finish_date=t.actual_finish_date,
                earliest_start_date=t.earliest_start_date,
                fixed_start_date=t.fixed_start_date,
                fixed_due_date=t.fixed_due_date,
                active=t.is_active_branch,
                milestone_id=t.milestone_id,
            )
            for t in tasks
        ]
        index = {task.id: task for task in current_tasks}
        original = {task.id: task for task in tasks}
        candidate = dict(index)
        for patch in data.changes:
            if patch.task_id not in index:
                raise DomainValidationError("变更任务不属于本项目")
            task = candidate[patch.task_id]
            values = patch.model_dump(exclude_unset=True, exclude={"task_id"})
            if task.status == "COMPLETED" and values:
                raise DomainValidationError("已完成任务不接受排期变更；实际记录保持不变")
            if task.status == "IN_PROGRESS" and (
                "start_date" in values or "planned_duration_days" in values
            ):
                raise DomainValidationError("已开始任务请修改剩余工期，不能重排实际开始")
            if "due_date" in values:
                if values["due_date"] is None:
                    raise DomainValidationError("候选截止日期不能为空")
                values["requested_due_date"] = values.pop("due_date")
            if data.mode == "earliest" and values.get("start_date"):
                values["earliest_start_date"] = max(
                    values["start_date"],
                    values.get("earliest_start_date")
                    or task.earliest_start_date
                    or values["start_date"],
                )
            candidate[task.id] = replace(task, **values)
        option_map = {option.id: option for option in options}
        selections = {}
        for group in groups:
            chosen = [o.id for o in options if o.group_id == group.id and o.is_selected]
            if len(chosen) > 1:
                raise DomainValidationError("路线组存在多个当前选项，请先修正数据")
            selections[group.id] = chosen[0] if chosen else None
        proposed_selections = dict(selections)
        dispositions = []
        for selection in data.selections:
            option = option_map.get(selection.option_id)
            if (
                option is None
                or option.group_id != selection.group_id
                or selection.group_id not in selections
            ):
                raise DomainValidationError("候选路线不属于本项目路线组")
            proposed_selections[selection.group_id] = selection.option_id
        for row in tasks:
            if row.branch_option_id is None:
                continue
            option = option_map.get(row.branch_option_id)
            if option is None:
                raise DomainValidationError("任务引用了本项目以外的路线选项")
            if row.is_active_branch != (selections[option.group_id] == option.id):
                raise DomainValidationError("任务激活标记与路线组选择不一致，请先修正数据")
            selected = proposed_selections[option.group_id] == option.id
            status = candidate[row.id].status
            if selections[option.group_id] != proposed_selections[option.group_id]:
                if not selected and row.is_active_branch and status in ("TODO", "IN_PROGRESS"):
                    dispositions.append(
                        {
                            "task_id": row.id,
                            "from_status": status,
                            "to_status": "CANCELLED",
                            "reason": "退出执行路线",
                        }
                    )
                    status = "CANCELLED"
                elif selected and status == "CANCELLED" and row.branch_suspended_status:
                    status = "IN_PROGRESS" if row.actual_start_date else "TODO"
                    dispositions.append(
                        {
                            "task_id": row.id,
                            "from_status": "CANCELLED",
                            "to_status": status,
                            "reason": "恢复被路线切换中止的工作，保留实际开始",
                        }
                    )
            candidate[row.id] = replace(candidate[row.id], active=selected, status=status)
        raw_links = [
            ScheduleLink(link.source_id, link.target_id, link.link_type.value, link.lag_days)
            for link in links
        ]
        proposed_links = (
            [ScheduleLink(**link.model_dump()) for link in data.links]
            if data.links is not None
            else raw_links
        )
        current_links, current_diagnostics = self._route_graph(
            current_tasks, raw_links, original, groups, options, selections
        )
        candidate_tasks = list(candidate.values())
        candidate_links, candidate_diagnostics = self._route_graph(
            candidate_tasks, proposed_links, original, groups, options, proposed_selections
        )
        target = (
            data.project_target_date
            if "project_target_date" in data.model_fields_set
            else project.target_date
        )
        common: dict[str, Any] = {
            "calendar": calendar,
            "project_id": project_id,
            "as_of": as_of,
            "project_start": project.start_date,
        }
        current_result = schedule(
            current_tasks, current_links, project_target=project.target_date, **common
        )
        candidate_result = schedule(
            candidate_tasks, candidate_links, project_target=target, mode=data.mode, **common
        )
        self._milestones(current_result, current_tasks, milestones)
        self._milestones(candidate_result, candidate_tasks, milestones)
        for result, diagnostics in (
            (current_result, current_diagnostics),
            (candidate_result, candidate_diagnostics),
        ):
            if diagnostics:
                result.feasible = False
                result.conflicts.extend(diagnostics)
                result.tasks = []
                result.project_finish_date = None
                result.target_variance_workdays = None
                result.target_variance_calendar_days = None
                result.critical_task_ids = []
                result.critical_links = []
                result.critical_path = []
        baseline = self.db.scalar(
            select(PlanVersion)
            .where(
                PlanVersion.project_id == project_id,
                PlanVersion.kind.in_(["BASELINE", "MIGRATION_BASELINE"]),
            )
            .order_by(PlanVersion.version)
            .limit(1)
        )
        baseline_tasks = (
            {row["id"]: row for row in baseline.snapshot.get("tasks", [])} if baseline else {}
        )
        baseline_data = (
            {
                "version": baseline.version,
                "kind": baseline.kind,
                "created_at": baseline.created_at,
                "project_target_date": baseline.snapshot.get("project", {}).get("target_date"),
            }
            if baseline
            else None
        )
        changed = []
        for computed in candidate_result.tasks:
            before = index[computed.task_id]
            if (
                computed.start_date != before.start_date
                or computed.finish_date != before.due_date
                or computed.task_id in {p.task_id for p in data.changes}
            ):
                changed.append(
                    {
                        "task_id": computed.task_id,
                        "task_name": computed.task_name,
                        "baseline_start_date": baseline_tasks.get(computed.task_id, {}).get(
                            "start_date"
                        ),
                        "baseline_due_date": baseline_tasks.get(computed.task_id, {}).get(
                            "due_date"
                        ),
                        "current_start_date": before.start_date,
                        "current_due_date": before.due_date,
                        "predicted_start_date": computed.start_date,
                        "predicted_finish_date": computed.finish_date,
                        "start_delta_workdays": calendar.delta(
                            before.start_date, computed.start_date
                        )
                        if before.start_date
                        else None,
                        "finish_delta_workdays": calendar.delta(
                            before.due_date, computed.finish_date
                        )
                        if before.due_date
                        else None,
                    }
                )
        latest = self.db.scalar(
            select(PlanVersion.version)
            .where(PlanVersion.project_id == project_id)
            .order_by(PlanVersion.version.desc())
            .limit(1)
        )
        forecast_delta = (
            calendar.delta(current_result.project_finish_date, candidate_result.project_finish_date)
            if current_result.project_finish_date and candidate_result.project_finish_date
            else None
        )
        return {
            "project_id": project_id,
            "as_of": as_of,
            "mode": data.mode,
            "snapshot_token": token,
            "calendar_version": calendar_data["version"],
            "baseline": baseline_data,
            "latest_saved_plan_version": latest,
            "current_target_date": project.target_date,
            "proposed_target_date": target,
            "current": asdict(current_result),
            "candidate": asdict(candidate_result),
            "changes": changed,
            "branch_dispositions": dispositions,
            "effective_links": [asdict(link) for link in candidate_links],
            "excluded_task_ids": sorted(
                t.id for t in candidate_tasks if not t.active or t.status == "CANCELLED"
            ),
            "forecast_delta_workdays": forecast_delta,
            "read_only": True,
            "capacity_constraints_applied": False,
            "notices": [
                "仅为日期预测，未修改当前计划或实际记录",
                "不计算人员资源容量约束",
                "行动项日期保持独立；尚无跟随任务的联动规则",
                "最早可行方案未校验外部预约或冻结区间；已录入的固定日期会被保护",
            ],
        }

    def forecast(self, project_id: int, actor: User) -> dict[str, Any]:
        """The current plan's predicted finish and critical path, for display.

        This is the same engine run the preview uses, with no candidate change
        applied. It is a prediction: it never edits the plan and it never moves
        the committed target date.
        """
        preview = self.preview(project_id, SchedulePreviewInput(), actor)
        current = preview["current"]
        finish = current["project_finish_date"]
        target = preview["current_target_date"]
        by_id = {row["task_id"]: row for row in current["tasks"]}
        variance = current["target_variance_workdays"]
        if finish is None:
            verdict = "UNKNOWN"
        elif target is None:
            verdict = "NO_TARGET"
        elif finish > target:
            verdict = "BEHIND"
        else:
            verdict = "ON_TRACK"
        return {
            "project_id": project_id,
            "as_of": preview["as_of"],
            "computable": finish is not None,
            "verdict": verdict,
            "predicted_finish_date": finish,
            "target_date": target,
            "variance_workdays": variance,
            "variance_calendar_days": current["target_variance_calendar_days"],
            "critical_task_ids": current["critical_task_ids"],
            "critical_path": [
                {
                    "task_id": task_id,
                    "task_name": by_id[task_id]["task_name"],
                    "status": by_id[task_id]["status"],
                    "start_date": by_id[task_id]["start_date"],
                    "finish_date": by_id[task_id]["finish_date"],
                    "total_float_workdays": by_id[task_id]["total_float_workdays"],
                }
                for task_id in current["critical_path"]
                if task_id in by_id
            ],
            "floats": {
                str(row["task_id"]): {
                    "predicted_start_date": row["start_date"],
                    "predicted_finish_date": row["finish_date"],
                    "total_float_workdays": row["total_float_workdays"],
                    "free_float_workdays": row["free_float_workdays"],
                    "critical": row["critical"],
                }
                for row in current["tasks"]
            },
            "conflicts": current["conflicts"],
            "warnings": current["warnings"],
            "excluded_task_ids": preview["excluded_task_ids"],
            "calendar_version": preview["calendar_version"],
            "notices": [
                "预测完成日期由当前计划、依赖和工作日历推算，不代表已承诺的目标日期发生变化",
                "关键路径上的任务没有机动时间，任何一天的拖延都会推迟整个项目",
                "不计算人员资源容量约束",
            ],
        }

    @staticmethod
    def _milestones(
        result: ScheduleResult, tasks: list[ScheduleTask], milestones: list[Milestone]
    ) -> None:
        membership = {task.id: task.milestone_id for task in tasks}
        for milestone in milestones:
            if milestone.status != "PLANNED" or milestone.target_date is None:
                continue
            finishes = [
                task.finish_date
                for task in result.tasks
                if membership[task.task_id] == milestone.id
            ]
            if finishes and max(finishes) > milestone.target_date:
                result.error(
                    "MILESTONE_TARGET_EXCEEDED",
                    f"里程碑“{milestone.name}”无法按目标日期达成",
                    [t.task_id for t in result.tasks if membership[t.task_id] == milestone.id],
                )

    @staticmethod
    def _route_graph(
        tasks: list[ScheduleTask],
        links: list[ScheduleLink],
        original: dict[int, Task],
        groups: list[BranchGroup],
        options: list[BranchOption],
        selections: dict[int, int | None],
    ) -> tuple[list[ScheduleLink], list[Diagnostic]]:
        by_id = {task.id: task for task in tasks}
        active = {task.id for task in tasks if task.active and task.status != "CANCELLED"}
        option_group = {option.id: option.group_id for option in options}
        group_map = {group.id: group for group in groups}
        diagnostics = []
        filtered = []
        for link in links:
            if link.source_id not in by_id or link.target_id not in by_id:
                filtered.append(link)  # The engine reports missing/cross-project references.
                continue
            if link.source_id in active and link.target_id in active:
                filtered.append(link)
                continue
            # Boundary rewiring only suppresses unused alternatives with declared boundaries.
            inactive = [tid for tid in (link.source_id, link.target_id) if tid not in active]
            alternative_groups: set[int] = set()
            for tid in inactive:
                option_id = original[tid].branch_option_id
                if option_id is not None and option_id in option_group and not by_id[tid].active:
                    alternative_groups.add(option_group[option_id])
            if alternative_groups:
                if link.source_id in active or link.target_id in active:
                    group = group_map[next(iter(alternative_groups))]
                    outside = link.source_id if link.source_id in active else link.target_id
                    if outside not in (group.entry_task_id, group.exit_task_id):
                        diagnostics.append(
                            Diagnostic(
                                "UNDECLARED_BRANCH_BOUNDARY",
                                "备用路线与当前任务的连线不经过声明的入口/汇合；请明确边界",
                                [link.source_id, link.target_id],
                            )
                        )
                continue
            filtered.append(link)
        pairs = {(link.source_id, link.target_id) for link in filtered}
        for group in groups:
            group_options = [option.id for option in options if option.group_id == group.id]
            if not group_options:
                continue
            selected = selections[group.id]
            if selected is None:
                diagnostics.append(
                    Diagnostic("NO_SELECTED_OPTION", f"路线组“{group.name}”尚未选择执行选项")
                )
                continue
            members = {
                task.id
                for task in tasks
                if original[task.id].branch_option_id == selected and task.id in active
            }
            if not members:
                diagnostics.append(
                    Diagnostic("EMPTY_SELECTED_OPTION", f"路线组“{group.name}”没有未取消的当前任务")
                )
                continue
            if group.entry_task_id is None or group.exit_task_id is None:
                diagnostics.append(
                    Diagnostic(
                        "MISSING_BRANCH_BOUNDARY",
                        f"路线组“{group.name}”缺少共享入口/汇合，无法可靠重接依赖",
                        sorted(members),
                    )
                )
                continue
            if group.entry_task_id not in active or group.exit_task_id not in active:
                diagnostics.append(
                    Diagnostic(
                        "INACTIVE_BRANCH_BOUNDARY",
                        "路线组共享入口/汇合不是当前有效节点",
                        [group.entry_task_id, group.exit_task_id],
                    )
                )
                continue
            internal = [
                link for link in filtered if link.source_id in members and link.target_id in members
            ]
            roots = members - {link.target_id for link in internal}
            leaves = members - {link.source_id for link in internal}
            for source_id, target_id in [(group.entry_task_id, tid) for tid in sorted(roots)] + [
                (tid, group.exit_task_id) for tid in sorted(leaves)
            ]:
                if (source_id, target_id) not in pairs:
                    filtered.append(ScheduleLink(source_id, target_id, synthetic=True))
                    pairs.add((source_id, target_id))
        return filtered, diagnostics
