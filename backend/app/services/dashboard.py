"""Dashboard aggregation — deterministic counts and project summaries."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.permissions import can_view_full_project
from app.models.project import ProjectRiskLevel
from app.models.task import Task
from app.models.user import User
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.schemas.dashboard import DashboardProjectItem, DashboardResponse
from app.services.business_clock import BusinessClock
from app.services.management_attention import ManagementAttentionService


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)
        self.management_attention = ManagementAttentionService(db)

    def get_dashboard(
        self,
        user: User,
        *,
        today: date | None = None,
        now: datetime | None = None,
    ) -> DashboardResponse:
        clock = BusinessClock()
        today = today or clock.today()
        now = now or clock.now().astimezone(UTC)
        visible = [
            project
            for project in self.projects.list_for_user(user)
            if can_view_full_project(self.db, user, project)
        ]
        project_ids = [project.id for project in visible]
        tasks_by_project = self.tasks.list_active_by_project_ids(project_ids)

        project_items: list[DashboardProjectItem] = []
        normal_count = 0
        at_risk_count = 0
        delayed_count = 0

        for project in visible:
            focus_task = self._pick_focus_task(tasks_by_project.get(project.id, []))
            owner_name = project.owner.name if project.owner else str(project.owner_id)
            project_items.append(
                DashboardProjectItem(
                    project_id=project.id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    status=project.status,
                    risk_level=project.risk_level,
                    owner=owner_name,
                    current_focus=focus_task.task_name if focus_task else None,
                    next_deadline=focus_task.due_date if focus_task else None,
                )
            )
            if project.risk_level == ProjectRiskLevel.NORMAL:
                normal_count += 1
            elif project.risk_level == ProjectRiskLevel.AT_RISK:
                at_risk_count += 1
            elif project.risk_level == ProjectRiskLevel.DELAYED:
                delayed_count += 1

        attention_items = self.management_attention.get_management_attention_items(
            user,
            today=today,
            now=now,
        )

        return DashboardResponse(
            project_total=len(visible),
            normal_count=normal_count,
            at_risk_count=at_risk_count,
            delayed_count=delayed_count,
            project_items=project_items,
            management_attention_count=len(attention_items),
        )

    @staticmethod
    def _pick_focus_task(tasks: list[Task]) -> Task | None:
        active = [task for task in tasks if task.is_execution_active]
        if not active:
            return None
        return min(
            active,
            key=lambda task: (task.due_date is None, task.due_date or date.max, task.id),
        )
