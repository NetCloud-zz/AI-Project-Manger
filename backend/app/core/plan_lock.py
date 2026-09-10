"""Cooperating ORM writers lock the project before DML, including legacy APIs/Agent.

This prevents task/link inserts and updates racing S3's final snapshot check.
Direct external SQL writers must follow the same project-lock protocol.
"""

from sqlalchemy import event, select
from sqlalchemy.orm import Session


@event.listens_for(Session, "before_flush")
def lock_changed_projects(session: Session, flush_context: object, instances: object) -> None:
    from app.models.planning import BranchOption, TaskParticipant
    from app.models.project import Project
    from app.models.task import Task

    ids: set[int] = set()
    for row in session.new | session.dirty | session.deleted:
        if isinstance(row, Project):
            if row.id is not None:
                ids.add(row.id)
        elif isinstance(row, BranchOption):
            from app.models.planning import BranchGroup

            group = session.get(BranchGroup, row.group_id)
            if group:
                ids.add(group.project_id)
        elif isinstance(row, TaskParticipant):
            task = session.get(Task, row.task_id)
            if task:
                ids.add(task.project_id)
        elif getattr(row, "project_id", None) is not None:
            ids.add(row.project_id)
    if ids:
        session.execute(
            select(Project.id)
            .where(Project.id.in_(sorted(ids)))
            .order_by(Project.id)
            .with_for_update()
        )
