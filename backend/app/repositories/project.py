"""Project data access."""

from __future__ import annotations

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.planning import ProjectMember
from app.models.project import Project, ProjectStatus, project_owners
from app.models.task import Task
from app.models.user import User, UserRole


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _with_owners(self) -> Select[tuple[Project]]:
        return select(Project).options(
            joinedload(Project.owner),
            selectinload(Project.owners),
        )

    def get_by_id(self, project_id: int) -> Project | None:
        return self.db.scalar(self._with_owners().where(Project.id == project_id))

    def get_by_code(self, project_code: str) -> Project | None:
        return self.db.scalar(self._with_owners().where(Project.project_code == project_code))

    def list_all(self) -> list[Project]:
        return list(self.db.scalars(self._with_owners().order_by(Project.id)).unique().all())

    def list_by_status(self, status: ProjectStatus) -> list[Project]:
        stmt = self._with_owners().where(Project.status == status).order_by(Project.id)
        return list(self.db.scalars(stmt).unique().all())

    def list_for_user(self, user: User) -> list[Project]:
        stmt = self._with_owners().order_by(Project.id.desc())
        if user.role in (UserRole.ADMIN, UserRole.EXECUTIVE):
            return list(self.db.scalars(stmt).unique().all())
        explicit = select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id, ProjectMember.is_active.is_(True)
        )
        if user.role == UserRole.PROJECT_OWNER:
            co_owned = select(project_owners.c.project_id).where(
                project_owners.c.user_id == user.id
            )
            stmt = stmt.where(
                or_(Project.owner_id == user.id, Project.id.in_(co_owned), Project.id.in_(explicit))
            )
            return list(self.db.scalars(stmt).unique().all())
        participated = select(Task.project_id).where(Task.owner_id == user.id).distinct().subquery()
        stmt = stmt.where(
            or_(Project.id.in_(select(participated.c.project_id)), Project.id.in_(explicit))
        )
        return list(self.db.scalars(stmt).unique().all())

    def add(self, project: Project) -> Project:
        self.db.add(project)
        self.db.flush()
        return project

    def save(self, project: Project) -> Project:
        self.db.add(project)
        self.db.flush()
        return project

    def delete(self, project: Project) -> None:
        self.db.delete(project)
        self.db.flush()
