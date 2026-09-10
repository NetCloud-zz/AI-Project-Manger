"""Solution advisor orchestration for issues."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.solution_advisor import (
    SolutionAdvisor,
    SolutionAdvisorInput,
    serialize_ai_suggested_solution,
)
from app.core.config import get_settings
from app.models.issue import Issue
from app.repositories.issue import IssueRepository
from app.repositories.progress_update import ProgressUpdateRepository
from app.services.advice import AdviceService
from app.services.audit import AuditService
from app.services.exceptions import IssueNotFoundError
from app.services.project_context import ProjectContextService


class SolutionAdvisorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.issues = IssueRepository(db)
        self.progress = ProgressUpdateRepository(db)
        self.audit = AuditService(db)
        self.context = ProjectContextService(db)
        self.advice_records = AdviceService(db)
        self.advisor = SolutionAdvisor()
        self.settings = get_settings()

    async def generate_and_save(
        self,
        issue_id: int,
        *,
        actor_id: int | None = None,
        ip_address: str | None = None,
    ) -> Issue:
        issue = self.issues.get_by_id(issue_id)
        if issue is None:
            raise IssueNotFoundError

        task = issue.task
        project = issue.project
        if project is None:
            raise IssueNotFoundError

        recent = self.progress.list_by_task(task.id, limit=5) if task else []
        recent_text = [item.raw_content for item in recent]
        historical = self.progress.list_by_task(task.id, limit=15) if task else []
        historical_text = [item.raw_content for item in reversed(historical)]

        # Bounded, ranked, id-carrying evidence — not a dump of the project.
        bundle = self.context.for_issue(issue)

        advice = await self.advisor.advise(
            SolutionAdvisorInput(
                project_goal=project.goal,
                project_code=project.project_code,
                task_name=task.task_name if task else None,
                task_due_date=task.due_date.isoformat() if task else None,
                project_target_date=(
                    project.target_date.isoformat() if project.target_date else None
                ),
                issue_title=issue.title,
                issue_description=issue.description,
                issue_severity=issue.severity.value,
                issue_status=issue.status.value,
                recent_progress=recent_text,
                historical_context=historical_text,
                evidence=bundle.lines(),
                coverage_note=_coverage_note(bundle),
                known_data_gaps=bundle.data_gaps,
                known_participants=self.context.participant_names(project.id),
            )
        )

        old_snapshot = self.audit.issue_to_dict(issue)
        issue.suggested_solution = serialize_ai_suggested_solution(advice)
        self.issues.save(issue)
        new_snapshot = self.audit.issue_to_dict(issue)

        # The issue field holds the latest text; the record holds the history,
        # the evidence it was built on, and room for the adoption decision.
        self.advice_records.record_generated(
            issue,
            advice,
            bundle,
            actor_id=actor_id,
            model=self.settings.LLM_MODEL_REASONING,
        )

        self.audit.record(
            action="issue.ai_advise",
            resource_type="issue",
            resource_id=str(issue.id),
            user_id=actor_id,
            old_value=old_snapshot,
            new_value=new_snapshot,
            ip_address=ip_address,
        )
        return self.issues.get_by_id(issue.id) or issue


def _coverage_note(bundle) -> str:  # type: ignore[no-untyped-def]
    coverage = bundle.coverage
    included = coverage.get("included", {})
    parts = "、".join(f"{key} {value} 条" for key, value in sorted(included.items()))
    excluded = "；".join(coverage.get("excluded", []))
    return (
        f"本次共选取 {parts or '0 条'}；项目共有 "
        f"{coverage.get('project_tasks_total', 0)} 个任务，其中执行中 "
        f"{coverage.get('execution_active_tasks', 0)} 个。未纳入：{excluded}"
    )
