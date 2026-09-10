"""Project and task access control.

Shared object permissions for API and Agent. EXECUTIVE is read-only.
Explicit project membership grants basic visibility; task assignments or explicit
participation grant access to individual tasks.
"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.issue import Issue
from app.models.planning import ProjectMember, TaskParticipant
from app.models.project import Project, project_owners
from app.models.task import Task
from app.models.user import User, UserRole


def user_has_task_in_project(db: Session, user_id: int, project_id: int) -> bool:
    stmt = select(exists().where(Task.project_id == project_id, Task.owner_id == user_id))
    return bool(db.scalar(stmt))


def user_is_project_owner(db: Session, user_id: int, project: Project) -> bool:
    """True when the user is the primary owner or listed in project_owners."""
    if project.owner_id == user_id:
        return True
    # Prefer the already-loaded relationship when available.
    if "owners" in project.__dict__:
        return any(owner.id == user_id for owner in project.owners)
    stmt = select(
        exists().where(
            project_owners.c.project_id == project.id,
            project_owners.c.user_id == user_id,
        )
    )
    return bool(db.scalar(stmt))


def can_view_project(db: Session, user: User, project: Project) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
        return True
    if user_is_project_owner(db, user.id, project):
        return True
    member = db.get(ProjectMember, (project.id, user.id))
    return bool(member and member.is_active) or user_has_task_in_project(db, user.id, project.id)


def can_view_full_project(db: Session, user: User, project: Project) -> bool:
    """Unfiltered plans and generated summaries can contain task-private details."""
    return user.role in (UserRole.ADMIN, UserRole.EXECUTIVE) or can_modify_project(
        user, project, db
    )


def can_modify_project(user: User, project: Project, db: Session | None = None) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    if user.role == UserRole.PROJECT_OWNER:
        if db is not None:
            return user_is_project_owner(db, user.id, project)
        return project.owner_id == user.id or any(
            owner.id == user.id for owner in getattr(project, "owners", []) or []
        )
    return False


def can_create_project(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.PROJECT_OWNER)


def can_modify_project_schedule(user: User, project: Project, db: Session | None = None) -> bool:
    """Project owners (incl. co-owners) and admins may change overall dates."""
    return can_modify_project(user, project, db)


def can_view_task(db: Session, user: User, task: Task) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
        return True
    if db.scalar(
        select(
            exists().where(
                TaskParticipant.task_id == task.id,
                TaskParticipant.user_id == user.id,
                TaskParticipant.user_id == ProjectMember.user_id,
                ProjectMember.project_id == task.project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.is_active.is_(True),
            )
        )
    ):
        return True
    if user.role == UserRole.MEMBER:
        return task.owner_id == user.id
    if task.owner_id == user.id:
        return True
    project = task.project
    if project and user.role == UserRole.PROJECT_OWNER:
        return user_is_project_owner(db, user.id, project)
    return bool(project and can_view_project(db, user, project))


def can_create_task(user: User, project: Project, db: Session | None = None) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    if user.role == UserRole.PROJECT_OWNER:
        return can_modify_project(user, project, db)
    return False


def can_modify_task_core(
    user: User, task: Task, project: Project, db: Session | None = None
) -> bool:
    """Change owner, due date, task name, or create/delete tasks."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    if user.role == UserRole.PROJECT_OWNER:
        return can_modify_project(user, project, db)
    return False


def can_modify_task_status(
    user: User, task: Task, project: Project, db: Session | None = None
) -> bool:
    """Task owners may update their own status; project owners manage everything."""
    if user.role == UserRole.EXECUTIVE:
        return False
    if can_modify_task_core(user, task, project, db):
        return True
    return task.owner_id == user.id


def can_view_issue(db: Session, user: User, issue: Issue) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
        return True
    task = issue.task
    project = issue.project
    if task and task.owner_id == user.id:
        return True
    if issue.reported_by == user.id:
        return True
    if (
        project
        and user.role == UserRole.PROJECT_OWNER
        and user_is_project_owner(db, user.id, project)
    ):
        return True
    if task:
        return can_view_task(db, user, task)
    return bool(project and can_view_project(db, user, project))


def can_create_issue(db: Session, user: User, project: Project) -> bool:
    """Log a problem manually. Anyone who can see the project except EXECUTIVE."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    return can_view_project(db, user, project)


def can_modify_issue(user: User, issue: Issue, db: Session | None = None) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    project = issue.project
    if not project or user.role != UserRole.PROJECT_OWNER:
        return False
    if db is not None:
        return user_is_project_owner(db, user.id, project)
    return project.owner_id == user.id or any(
        o.id == user.id for o in getattr(project, "owners", []) or []
    )


def can_request_issue_advice(user: User, issue: Issue) -> bool:
    """Request AI suggested solution — admin, project owner, reporter, or task owner."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    if issue.reported_by == user.id:
        return True
    task = issue.task
    if task and task.owner_id == user.id:
        return True
    project = issue.project
    return bool(
        project
        and user.role == UserRole.PROJECT_OWNER
        and (
            project.owner_id == user.id
            or any(o.id == user.id for o in getattr(project, "owners", []) or [])
        )
    )


def can_view_action_item(db: Session, user: User, item: ActionItem) -> bool:
    if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
        return True
    if user.id in (item.owner_id, item.created_by):
        return True
    project = item.project
    if (
        project
        and user.role == UserRole.PROJECT_OWNER
        and user_is_project_owner(db, user.id, project)
    ):
        return True
    return bool(project and can_view_project(db, user, project))


def can_create_action_item(db: Session, user: User, project: Project) -> bool:
    """Record who does what by when. Anyone who can see the project except EXECUTIVE."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    return can_view_project(db, user, project)


def can_modify_action_item(user: User, item: ActionItem, project: Project | None) -> bool:
    """Project owners manage everything; assignee and author manage their own item."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    if (
        project
        and user.role == UserRole.PROJECT_OWNER
        and (
            project.owner_id == user.id
            or any(o.id == user.id for o in getattr(project, "owners", []) or [])
        )
    ):
        return True
    return user.id in (item.owner_id, item.created_by)


def can_view_dashboard(user: User) -> bool:
    """Management dashboard — all projects for exec/admin, owned projects for PO."""
    return user.role in (UserRole.ADMIN, UserRole.EXECUTIVE, UserRole.PROJECT_OWNER)


def can_view_personal_dashboard(user: User) -> bool:
    """Members get a minimal personal task summary instead of management dashboard."""
    return user.role == UserRole.MEMBER


def can_submit_progress(user: User, task: Task, project: Project) -> bool:
    """Task owner submits daily progress; project owner may submit on behalf."""
    if user.role == UserRole.EXECUTIVE:
        return False
    if user.role == UserRole.ADMIN:
        return True
    if task.owner_id == user.id:
        return True
    return user.role == UserRole.PROJECT_OWNER and (
        project.owner_id == user.id
        or any(o.id == user.id for o in getattr(project, "owners", []) or [])
    )
