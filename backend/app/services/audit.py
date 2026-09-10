"""Audit log business logic."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.security import sanitize_for_audit
from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository


class AuditService:
    def __init__(self, db: Session) -> None:
        self.repo = AuditLogRepository(db)

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: int | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=sanitize_for_audit(old_value),
            new_value=sanitize_for_audit(new_value),
            ip_address=ip_address,
        )
        return self.repo.add(entry)

    def user_to_dict(self, user: Any) -> dict[str, Any]:
        """Serialize a User ORM instance for audit storage (no password fields)."""
        return {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "mobile": user.mobile,
            "department": user.department,
            "wechat_user_id": user.wechat_user_id,
            "oa_admin_id": getattr(user, "oa_admin_id", None),
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "status": user.status.value if hasattr(user.status, "value") else user.status,
        }

    def project_to_dict(self, project: Any) -> dict[str, Any]:
        owner_ids = (
            [o.id for o in project.owners]
            if getattr(project, "owners", None) is not None
            else [project.owner_id]
        )
        return {
            "id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "goal": project.goal,
            "owner_id": project.owner_id,
            "owner_ids": owner_ids,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "target_date": project.target_date.isoformat() if project.target_date else None,
            "status": project.status.value if hasattr(project.status, "value") else project.status,
            "risk_level": (
                project.risk_level.value
                if hasattr(project.risk_level, "value")
                else project.risk_level
            ),
        }

    def task_to_dict(self, task: Any) -> dict[str, Any]:
        return {
            "id": task.id,
            "project_id": task.project_id,
            "task_name": task.task_name,
            **{
                key: (
                    getattr(task, key).isoformat()
                    if hasattr(getattr(task, key), "isoformat")
                    else getattr(task, key)
                )
                for key in (
                    "description",
                    "deliverable",
                    "acceptance_criteria",
                    "planned_duration_days",
                    "remaining_duration_days",
                    "actual_start_date",
                    "actual_finish_date",
                    "earliest_start_date",
                    "fixed_start_date",
                    "fixed_due_date",
                    "calendar_id",
                    "milestone_id",
                    "task_group_id",
                    "branch_option_id",
                )
            },
            "work_stream": task.work_stream,
            "owner_id": task.owner_id,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "progress_percent": task.progress_percent,
            "status": task.status.value if hasattr(task.status, "value") else task.status,
            "branch_root_id": task.branch_root_id,
            "branch_label": task.branch_label,
            "is_active_branch": task.is_active_branch,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    def task_link_to_dict(self, link: Any) -> dict[str, Any]:
        return {
            "id": link.id,
            "project_id": link.project_id,
            "source_id": link.source_id,
            "lag_days": link.lag_days,
            "target_id": link.target_id,
            "link_type": (
                link.link_type.value if hasattr(link.link_type, "value") else link.link_type
            ),
        }

    def action_item_to_dict(self, item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "task_id": item.task_id,
            "issue_id": item.issue_id,
            "owner_id": item.owner_id,
            "created_by": item.created_by,
            "title": item.title,
            "description": item.description,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status.value if hasattr(item.status, "value") else item.status,
            "priority": item.priority.value if hasattr(item.priority, "value") else item.priority,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        }

    def issue_to_dict(self, issue: Any) -> dict[str, Any]:
        return {
            "id": issue.id,
            "project_id": issue.project_id,
            "task_id": issue.task_id,
            "reported_by": issue.reported_by,
            "title": issue.title,
            "description": issue.description,
            "severity": (
                issue.severity.value if hasattr(issue.severity, "value") else issue.severity
            ),
            "status": issue.status.value if hasattr(issue.status, "value") else issue.status,
            "suggested_solution": issue.suggested_solution,
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
        }
