"""Project and task access control.

Shared object permissions for API and Agent. EXECUTIVE is read-only.
Project *management* is keyed off project ownership (primary or co-owner),
not the global PROJECT_OWNER role. That global role only gates creating
new projects and the management dashboard.
"""

from __future__ import annotations

from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.issue import Issue
from app.models.planning import ProjectMember, TaskParticipant
from app.models.project import Project, project_owners
from app.models.task import Task
from app.models.user import User, UserRole


def user_has_task_in_project(db: Session, user_id: int, project_id: int) -> bool:
    as_primary = select(exists().where(Task.project_id == project_id, Task.owner_id == user_id))
    if db.scalar(as_primary):
        return True
    as_co_owner = select(
        exists().where(
            Task.project_id == project_id,
            TaskParticipant.task_id == Task.id,
            TaskParticipant.user_id == user_id,
            TaskParticipant.role == "OWNER",
        )
    )
    return bool(db.scalar(as_co_owner))


def user_is_task_owner(db: Session | None, user_id: int, task: Task) -> bool:
    """True when the user is the primary owner or an OWNER task participant."""
    if task.owner_id == user_id:
        return True
    if db is None:
        return False
    return bool(
        db.scalar(
            select(
                exists().where(
                    TaskParticipant.task_id == task.id,
                    TaskParticipant.user_id == user_id,
                    TaskParticipant.role == "OWNER",
                )
            )
        )
    )


def user_is_project_owner(
    db: Session | None, user_id: int, project: Project
) -> bool:
    """True when the user is the primary owner or listed in project_owners.

    ``db`` may be omitted when ``project.owners`` is already loaded (or when
    only ``owner_id`` needs to be checked).
    """
    if project.owner_id == user_id:
        return True
    if "owners" in project.__dict__:
        return any(owner.id == user_id for owner in project.owners)
    if db is None:
        return any(owner.id == user_id for owner in getattr(project, "owners", []) or [])
    stmt = select(
        exists().where(
            project_owners.c.project_id == project.id,
            project_owners.c.user_id == user_id,
        )
    )
    return bool(db.scalar(stmt))


def project_ids_owned_by(user_id: int) -> Select[tuple[int]]:
    """Subselect of project ids where ``user_id`` is primary or co-owner."""
    co_owned = select(project_owners.c.project_id).where(project_owners.c.user_id == user_id)
    return select(Project.id).where(or_(Project.owner_id == user_id, Project.id.in_(co_owned)))


def _is_elevated_reader(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.EXECUTIVE)


def _write_gate(user: User) -> bool | None:
    """Return True/False for admin/executive; None means fall through to object checks."""
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.EXECUTIVE:
        return False
    return None


def can_view_project(db: Session, user: User, project: Project) -> bool:
    if _is_elevated_reader(user) or user_is_project_owner(db, user.id, project):
        return True
    member = db.get(ProjectMember, (project.id, user.id))
    return bool(member and member.is_active) or user_has_task_in_project(db, user.id, project.id)


def can_view_full_project(db: Session, user: User, project: Project) -> bool:
    """Unfiltered plans and generated summaries can contain task-private details."""
    return _is_elevated_reader(user) or can_modify_project(user, project, db)


def can_modify_project(user: User, project: Project, db: Session | None = None) -> bool:
    """Admins and the project's owners/co-owners, whatever their global role."""
    gate = _write_gate(user)
    if gate is not None:
        return gate
    return user_is_project_owner(db, user.id, project)


def can_create_project(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.PROJECT_OWNER)


def can_modify_project_schedule(user: User, project: Project, db: Session | None = None) -> bool:
    """Project owners (incl. co-owners) and admins may change overall dates."""
    return can_modify_project(user, project, db)


def can_view_task(db: Session, user: User, task: Task) -> bool:
    if _is_elevated_reader(user):
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
    if user_is_task_owner(db, user.id, task):
        return True
    project = task.project
    return bool(project and user_is_project_owner(db, user.id, project))


def can_create_task(user: User, project: Project, db: Session | None = None) -> bool:
    return can_modify_project(user, project, db)


def can_modify_task_core(
    user: User, task: Task, project: Project, db: Session | None = None
) -> bool:
    """Change owner, due date, task name, or create/delete tasks."""
    return can_modify_project(user, project, db)


def can_modify_task_status(
    user: User, task: Task, project: Project, db: Session | None = None
) -> bool:
    """Task owners may update their own status; project owners manage everything."""
    if user.role == UserRole.EXECUTIVE:
        return False
    return can_modify_task_core(user, task, project, db) or user_is_task_owner(
        db, user.id, task
    )


def can_view_issue(db: Session, user: User, issue: Issue) -> bool:
    if _is_elevated_reader(user):
        return True
    task = issue.task
    project = issue.project
    if task and user_is_task_owner(db, user.id, task):
        return True
    if issue.reported_by == user.id:
        return True
    if project and user_is_project_owner(db, user.id, project):
        return True
    if task:
        return can_view_task(db, user, task)
    return bool(project and can_view_project(db, user, project))


def can_create_issue(db: Session, user: User, project: Project) -> bool:
    """Log a problem manually. Anyone who can see the project except EXECUTIVE."""
    gate = _write_gate(user)
    if gate is not None:
        return gate
    return can_view_project(db, user, project)


def can_modify_issue(user: User, issue: Issue, db: Session | None = None) -> bool:
    gate = _write_gate(user)
    if gate is not None:
        return gate
    project = issue.project
    return bool(project and user_is_project_owner(db, user.id, project))


def can_request_issue_advice(
    user: User, issue: Issue, db: Session | None = None
) -> bool:
    """Request AI suggested solution — admin, project owner, reporter, or task owner."""
    gate = _write_gate(user)
    if gate is not None:
        return gate
    if issue.reported_by == user.id:
        return True
    task = issue.task
    if task and user_is_task_owner(db, user.id, task):
        return True
    project = issue.project
    return bool(project and user_is_project_owner(db, user.id, project))


def can_view_action_item(db: Session, user: User, item: ActionItem) -> bool:
    if _is_elevated_reader(user) or user.id in (item.owner_id, item.created_by):
        return True
    project = item.project
    return bool(project and can_view_project(db, user, project))


def can_create_action_item(db: Session, user: User, project: Project) -> bool:
    """Record who does what by when. Anyone who can see the project except EXECUTIVE."""
    gate = _write_gate(user)
    if gate is not None:
        return gate
    return can_view_project(db, user, project)


def can_modify_action_item(user: User, item: ActionItem, project: Project | None) -> bool:
    """Project owners manage everything; assignee and author manage their own item."""
    gate = _write_gate(user)
    if gate is not None:
        return gate
    if project and user_is_project_owner(None, user.id, project):
        return True
    return user.id in (item.owner_id, item.created_by)


def can_view_dashboard(user: User) -> bool:
    """Management dashboard — all projects for exec/admin, owned projects for PO."""
    return user.role in (UserRole.ADMIN, UserRole.EXECUTIVE, UserRole.PROJECT_OWNER)


def can_view_personal_dashboard(user: User) -> bool:
    """Members get a minimal personal task summary instead of management dashboard."""
    return user.role == UserRole.MEMBER


def can_submit_progress(
    user: User, task: Task, project: Project, db: Session | None = None
) -> bool:
    """Task owner submits daily progress; project owner may submit on behalf."""
    if user.role == UserRole.EXECUTIVE:
        return False
    if user.role == UserRole.ADMIN or user_is_task_owner(db, user.id, task):
        return True
    return user_is_project_owner(db, user.id, project)
