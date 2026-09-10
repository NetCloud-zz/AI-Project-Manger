"""Stop a direct edit from silently moving dates that belong to other tasks.

S3 built the change-proposal path so that a multi-task reschedule is previewed,
confirmed and applied in one transaction. The old REST and Gantt endpoints kept
writing straight to the database, which meant a single date edit could leave the
dependency graph and the stored dates disagreeing with each other.

The rule this module enforces is narrow on purpose:

* Editing a **plan** field (dates, durations, constraints, dependencies) is an
  intent. If the schedule engine says it would move any *other* task, the edit
  is refused and the caller is told to use a change proposal.
* Recording a **fact** (status, actual dates, remaining work) is never refused.
  You cannot require an approval workflow to report what already happened, even
  though the forecast will move as a result.

If the current plan cannot be computed at all, the edit is allowed through.
Blocking every write on a project whose data is already broken would leave no
way to repair it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task, TaskLink
from app.models.user import User
from app.schemas.scheduling import ScheduleLinkInput, SchedulePreviewInput, ScheduleTaskPatch

#: Task columns that express intent about when work should happen.
PLAN_FIELDS = frozenset(
    {
        "start_date",
        "due_date",
        "planned_duration_days",
        "earliest_start_date",
        "fixed_start_date",
        "fixed_due_date",
    }
)

#: Task columns that record what actually happened. Never gated.
FACT_FIELDS = frozenset(
    {
        "status",
        "actual_start_date",
        "actual_finish_date",
        "remaining_duration_days",
        "progress_percent",
    }
)

#: Any change to these means a stored forecast or risk verdict may be stale.
SCHEDULE_RELEVANT_FIELDS = PLAN_FIELDS | FACT_FIELDS


class ScheduleImpactRequiresProposal(Exception):
    """The edit is legitimate but ripples beyond the object being edited."""

    def __init__(self, impacted: list[dict[str, Any]], action: str) -> None:
        self.impacted = impacted
        self.action = action
        names = "、".join(row["task_name"] for row in impacted[:3])
        more = "" if len(impacted) <= 3 else f" 等 {len(impacted)} 个任务"
        self.message = (
            f"{action}会让{names}{more}的日期发生变化。"
            "涉及多个任务的改期请走变更方案：先预览完整差异，确认后一次性执行。"
        )
        super().__init__(self.message)


class ScheduleGuard:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --------------------------------------------------------------- entries

    def check_task_edit(
        self, task: Task, updates: dict[str, Any], actor: User, *, action: str = "这次修改"
    ) -> None:
        """Refuse a plan-field edit on one task that would move other tasks."""
        patch = {
            field: value
            for field, value in updates.items()
            if field in PLAN_FIELDS and value != getattr(task, field)
        }
        if not patch:
            return
        self._assert_local(
            task.project_id,
            actor,
            SchedulePreviewInput(changes=[ScheduleTaskPatch(task_id=task.id, **patch)]),
            exempt={task.id},
            action=action,
        )

    def check_links(
        self, project_id: int, links: list[TaskLink], actor: User, *, action: str
    ) -> None:
        """Refuse a dependency change that would force a reschedule."""
        self._assert_local(
            project_id,
            actor,
            SchedulePreviewInput(
                links=[
                    ScheduleLinkInput(
                        source_id=link.source_id,
                        target_id=link.target_id,
                        link_type=link.link_type.value,
                        lag_days=link.lag_days,
                    )
                    for link in links
                ]
            ),
            exempt=set(),
            action=action,
        )

    def check_project_start(self, project: Project, new_start: date | None, actor: User) -> None:
        """Refuse a project start date that would push the tasks underneath it."""
        if new_start == project.start_date:
            return
        # The project start is read straight off the ORM row, so a single
        # preview would apply it to both sides of the comparison. Schedule the
        # plan twice instead: once as it stands, once as proposed.
        before = self._schedule(project.id, actor, SchedulePreviewInput())
        with self._temporarily(project, "start_date", new_start):
            after = self._schedule(project.id, actor, SchedulePreviewInput())
        self._compare(before, after, exempt=set(), action="调整项目开始日期")

    # ------------------------------------------------------------- staleness

    @staticmethod
    def touches_schedule(before: dict[str, Any], after: dict[str, Any]) -> bool:
        """True when a stored forecast or risk verdict may no longer hold."""
        return any(before.get(field) != after.get(field) for field in SCHEDULE_RELEVANT_FIELDS)

    # ---------------------------------------------------------------- shared

    def _assert_local(
        self,
        project_id: int,
        actor: User,
        data: SchedulePreviewInput,
        *,
        exempt: set[int],
        action: str,
    ) -> None:
        from app.services.scheduling import SchedulingService

        preview = SchedulingService(self.db).preview(project_id, data, actor)
        self._compare(preview["current"], preview["candidate"], exempt=exempt, action=action)

    def _schedule(self, project_id: int, actor: User, data: SchedulePreviewInput) -> dict[str, Any]:
        from app.services.scheduling import SchedulingService

        return SchedulingService(self.db).preview(project_id, data, actor)["current"]

    @staticmethod
    def _compare(
        before_result: dict[str, Any],
        after_result: dict[str, Any],
        *,
        exempt: set[int],
        action: str,
    ) -> None:
        before = _dates(before_result)
        if not before:
            # The current plan is not computable, so no movement can be
            # attributed to this edit. Let the repair through.
            return
        after = _dates(after_result)
        names = {row["task_id"]: row["task_name"] for row in after_result["tasks"]}
        impacted = [
            {
                "task_id": task_id,
                "task_name": names.get(task_id, str(task_id)),
                "current_start_date": before[task_id][0],
                "current_finish_date": before[task_id][1],
                "predicted_start_date": dates[0],
                "predicted_finish_date": dates[1],
            }
            for task_id, dates in sorted(after.items())
            if task_id not in exempt and task_id in before and before[task_id] != dates
        ]
        if impacted:
            raise ScheduleImpactRequiresProposal(impacted, action)

    @contextmanager
    def _temporarily(self, instance: Any, field: str, value: Any) -> Iterator[None]:
        """Let the engine read a proposed value without ever persisting it.

        Autoflush is suspended because the dirty attribute would otherwise reach
        the database on the engine's very next SELECT.
        """
        original = getattr(instance, field)
        setattr(instance, field, value)
        try:
            with self.db.no_autoflush:
                yield
        finally:
            setattr(instance, field, original)


def _dates(result: dict[str, Any]) -> dict[int, tuple[Any, Any]]:
    return {row["task_id"]: (row["start_date"], row["finish_date"]) for row in result["tasks"]}


__all__ = [
    "FACT_FIELDS",
    "PLAN_FIELDS",
    "SCHEDULE_RELEVANT_FIELDS",
    "ScheduleGuard",
    "ScheduleImpactRequiresProposal",
]
