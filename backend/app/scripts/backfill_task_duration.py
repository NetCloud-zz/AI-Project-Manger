"""Derive planned_duration_days for legacy tasks that already carry both dates.

Usage:
    python -m app.scripts.backfill_task_duration                # dry run, prints a plan
    python -m app.scripts.backfill_task_duration --apply
    python -m app.scripts.backfill_task_duration --project PRJ-1001 --apply

Only tasks that have a start date and a due date are touched, and the duration
is counted in the project's own working days. Nothing is guessed: a task with a
missing date stays missing and keeps showing up in the integrity report, because
inventing a duration there would turn an unknown into a fake number.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.models.planning import WorkCalendar
from app.models.project import Project
from app.models.task import Task
from app.scheduling.calendar import CalendarRangeError, WorkingCalendar

DEFAULT_WEEKDAYS = [0, 1, 2, 3, 4]


def _calendar(db: Session, project: Project, earliest: date) -> WorkingCalendar:
    row = db.get(WorkCalendar, project.id)
    weekdays = list(row.weekdays) if row and row.weekdays else DEFAULT_WEEKDAYS
    exceptions = dict(row.exceptions) if row and row.exceptions else {}
    return WorkingCalendar(earliest, weekdays, exceptions)


def backfill(db: Session, project: Project) -> list[tuple[Task, int]]:
    candidates: list[tuple[Task, date, date]] = [
        (task, task.start_date, task.due_date)
        for task in db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.id))
        if task.planned_duration_days is None
        and task.start_date is not None
        and task.due_date is not None
        and task.due_date >= task.start_date
    ]
    if not candidates:
        return []
    calendar = _calendar(db, project, min(start for _, start, _ in candidates))
    planned: list[tuple[Task, int]] = []
    for task, start, due in candidates:
        try:
            days = calendar.finish(due) - calendar.start(start)
        except CalendarRangeError:
            continue
        if days >= 1:
            planned.append((task, days))
    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description="按工作日历回填任务计划工期")
    parser.add_argument("--project", help="仅处理指定项目编号（project_code）")
    parser.add_argument("--apply", action="store_true", help="实际写入；缺省仅预演")
    args = parser.parse_args()

    configure_logging()
    with SessionLocal() as db:
        query = select(Project).order_by(Project.id)
        if args.project:
            query = query.where(Project.project_code == args.project)
        projects = list(db.scalars(query))
        if args.project and not projects:
            print(f"项目 {args.project} 不存在", file=sys.stderr)
            return 2

        total = 0
        for project in projects:
            planned = backfill(db, project)
            if not planned:
                continue
            print(f"\n项目 {project.project_code}（{len(planned)} 个任务）")
            for task, days in planned:
                print(
                    f"  #{task.id} {task.task_name}："
                    f"{task.start_date} 至 {task.due_date} = {days} 个工作日"
                )
                if args.apply:
                    task.planned_duration_days = days
            total += len(planned)

        if args.apply:
            db.commit()
            print(f"\n已回填 {total} 个任务的计划工期。")
        else:
            print(f"\n预演：可回填 {total} 个任务。加 --apply 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
