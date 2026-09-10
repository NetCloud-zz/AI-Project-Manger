"""Background tasks."""

from __future__ import annotations

import asyncio
from datetime import date

from celery import Task as CeleryTask
from sqlalchemy.orm import Session, joinedload

from app.agents.progress_analyzer import ProgressAnalyzer, ProgressAnalyzerInput
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.progress_update import ProgressUpdate
from app.models.task import Task
from app.services.daily_summary import DailySummaryService
from app.services.issue import IssueService
from app.services.notification_delivery import NotificationDeliveryService
from app.services.progress import ProgressService
from app.services.risk_engine import RiskEngine
from app.services.scheduled_tracking import ScheduledTrackingService
from app.services.solution_advisor import SolutionAdvisorService
from app.workers.celery_app import celery_app
from app.workers.db import worker_db_session
from app.workers.idempotency import acquire_daily_run_lock
from app.workers.timezone import scheduler_today

logger = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.ping")
def ping() -> str:
    """Verify that the worker can receive and execute a task."""
    logger.info("worker.ping")
    return "pong"


@celery_app.task(
    name="app.workers.tasks.analyze_progress_update",
    bind=True,
    max_retries=0,
)
def analyze_progress_update(
    self: CeleryTask,
    progress_id: int,
    run_id: int | None = None,
) -> str:
    """Analyse a progress update asynchronously via the Progress Analyzer agent."""
    settings = get_settings()
    if not settings.llm_configured:
        logger.info("worker.analyze_progress_update.ai_disabled", progress_id=progress_id)
        if run_id is not None:
            with worker_db_session() as db:
                from app.services.ai_run import AIRunService

                AIRunService(db).mark_disabled(run_id)
                db.commit()
        return "ai_disabled"

    if run_id is not None:
        with worker_db_session() as db:
            from app.services.ai_run import AIRunService

            AIRunService(db).mark_running(run_id, model=settings.LLM_MODEL_FAST)
            db.commit()

    try:
        with worker_db_session() as db:
            result = asyncio.run(_run_analysis(db, progress_id))
        if run_id is not None:
            with worker_db_session() as db:
                from app.services.ai_run import AIRunService

                if result in {"ok", "already_analyzed"} or str(result).startswith("ok"):
                    AIRunService(db).mark_succeeded(run_id)
                elif result == "not_found":
                    AIRunService(db).mark_failed(run_id, error_code="not_found")
                else:
                    AIRunService(db).mark_succeeded(run_id)
                db.commit()
        return result
    except Exception:
        logger.exception("worker.analyze_progress_update.failed", progress_id=progress_id)
        try:
            with worker_db_session() as db:
                _mark_analysis_failed(db, progress_id)
                if run_id is not None:
                    from app.services.ai_run import AIRunService

                    AIRunService(db).mark_failed(run_id, error_code="provider_error")
                db.commit()
        except Exception:
            logger.exception(
                "worker.analyze_progress_update.mark_failed_error",
                progress_id=progress_id,
            )
        return "failed"


def _progress_already_analyzed(progress: ProgressUpdate) -> bool:
    """Skip duplicate AI work when Celery redelivers or enqueue is retried."""
    return progress.summary is not None or progress.ai_analysis_failed


async def _run_analysis(db: Session, progress_id: int) -> str:
    context = _load_context(db, progress_id)
    if context is None:
        logger.warning("worker.analyze_progress_update.not_found", progress_id=progress_id)
        return "not_found"

    progress, task, historical = context
    if _progress_already_analyzed(progress):
        logger.info(
            "worker.analyze_progress_update.already_analyzed",
            progress_id=progress_id,
            has_summary=progress.summary is not None,
            ai_analysis_failed=progress.ai_analysis_failed,
        )
        return "already_analyzed"

    raw_before = progress.raw_content

    analyzer = ProgressAnalyzer()
    analysis = await analyzer.analyze(
        ProgressAnalyzerInput(
            project_goal=task.project.goal,
            task_name=task.task_name,
            due_date=task.due_date,
            current_date=date.today(),
            historical_progress=historical,
            today_update=progress.raw_content,
        )
    )

    service = ProgressService(db)
    service.update_ai_fields(
        progress_id,
        summary=analysis.summary,
        ai_status=analysis.status.value,
        risk_detected=analysis.risk,
        ai_analysis_failed=False,
    )

    # Re-read task context after model latency; changed plans invalidate older submissions.
    db.refresh(task)
    db.flush()
    risk_engine = RiskEngine(db)
    if (
        analysis.issue_detected
        and analysis.issue is not None
        and task.is_execution_active
        and risk_engine.is_current_evidence(task, progress)
    ):
        created = IssueService(db).create_from_progress_analysis(
            task_id=task.id,
            reported_by=progress.user_id,
            issue=analysis.issue,
        )
        if created is not None:
            logger.info(
                "worker.analyze_progress_update.issue_created",
                progress_id=progress_id,
                issue_id=created.id,
                issue_title=created.title,
                severity=created.severity.value,
            )
        else:
            logger.info(
                "worker.analyze_progress_update.issue_deduplicated",
                progress_id=progress_id,
                issue_title=analysis.issue.title,
            )

    db.flush()
    risk_engine.evaluate_task(task)
    if task.project is not None:
        risk_engine.evaluate_project(task.project)

    refreshed = service.repo.get_by_id(progress_id)
    if refreshed is not None and refreshed.raw_content != raw_before:
        logger.error(
            "worker.analyze_progress_update.raw_content_mutated",
            progress_id=progress_id,
        )

    logger.info(
        "worker.analyze_progress_update.completed",
        progress_id=progress_id,
        status=analysis.status.value,
    )
    return "ok"


def _load_context(
    db: Session,
    progress_id: int,
) -> tuple[ProgressUpdate, Task, list[str]] | None:
    progress = (
        db.query(ProgressUpdate)
        .options(
            joinedload(ProgressUpdate.task).joinedload(Task.project),
        )
        .filter(ProgressUpdate.id == progress_id)
        .one_or_none()
    )
    if progress is None:
        return None

    task = progress.task
    prior = (
        db.query(ProgressUpdate)
        .filter(
            ProgressUpdate.task_id == task.id,
            ProgressUpdate.id != progress.id,
        )
        .order_by(ProgressUpdate.created_at.desc())
        .limit(10)
        .all()
    )
    historical = [item.raw_content for item in reversed(prior)]
    return progress, task, historical


def _mark_analysis_failed(db: Session, progress_id: int) -> None:
    ProgressService(db).update_ai_fields(progress_id, ai_analysis_failed=True)


@celery_app.task(name="app.workers.tasks.scan_daily_tasks")
def scan_daily_tasks() -> str:
    """Daily reminder for TODO / IN_PROGRESS tasks."""
    if not acquire_daily_run_lock("scan_daily_tasks"):
        return "skipped_duplicate"
    try:
        with worker_db_session() as db:
            sent = ScheduledTrackingService(db).scan_daily_tasks()
    except Exception:
        logger.exception("worker.scan_daily_tasks.failed")
        raise
    return f"sent:{sent}"


@celery_app.task(name="app.workers.tasks.scan_missing_progress")
def scan_missing_progress() -> str:
    """Notify owners who have not submitted progress today."""
    if not acquire_daily_run_lock("scan_missing_progress"):
        return "skipped_duplicate"
    try:
        with worker_db_session() as db:
            sent = ScheduledTrackingService(db).scan_missing_progress()
    except Exception:
        logger.exception("worker.scan_missing_progress.failed")
        raise
    return f"sent:{sent}"


@celery_app.task(name="app.workers.tasks.scan_risk")
def scan_risk() -> str:
    """Evaluate deterministic risk rules and send stale-progress notifications."""
    if not acquire_daily_run_lock("scan_risk"):
        return "skipped_duplicate"
    try:
        with worker_db_session() as db:
            result = RiskEngine(db).evaluate_all()
    except Exception:
        logger.exception("worker.scan_risk.failed")
        raise
    return (
        f"tasks:{result.tasks_updated},projects:{result.projects_updated},"
        f"notifications:{result.notifications_sent}"
    )


@celery_app.task(name="app.workers.tasks.dispatch_plan_notifications")
def dispatch_plan_notifications(limit: int | None = None) -> str:
    """Send queued plan-change notifications and record real delivery outcomes."""
    try:
        with worker_db_session() as db:
            counts = NotificationDeliveryService(db).dispatch_pending(limit)
            db.commit()
    except Exception:
        logger.exception("worker.dispatch_plan_notifications.failed")
        raise
    return f"sent:{counts['sent']},retry:{counts['retry']},failed:{counts['failed']}"


def enqueue_plan_notifications() -> None:
    """Nudge the outbox after a change is applied; Beat still sweeps on failure."""
    try:
        dispatch_plan_notifications.delay()
    except Exception as exc:
        logger.warning("worker.enqueue_plan_notifications_failed", error=str(exc))


def enqueue_analyze_progress(progress_id: int, *, run_id: int | None = None) -> None:
    """Enqueue progress analysis; no-op if broker unavailable."""
    try:
        if run_id is None:
            analyze_progress_update.delay(progress_id)
        else:
            analyze_progress_update.delay(progress_id, run_id=run_id)
    except Exception as exc:
        logger.warning("worker.enqueue_failed", progress_id=progress_id, error=str(exc))


@celery_app.task(
    name="app.workers.tasks.advise_issue",
    bind=True,
    max_retries=0,
)
def advise_issue(
    self: CeleryTask,
    issue_id: int,
    *,
    actor_id: int | None = None,
    ip_address: str | None = None,
    run_id: int | None = None,
) -> str:
    """Generate AI suggested solution for an issue asynchronously."""
    settings = get_settings()
    if not settings.llm_configured:
        logger.info("worker.advise_issue.ai_disabled", issue_id=issue_id)
        if run_id is not None:
            with worker_db_session() as db:
                from app.services.ai_run import AIRunService

                AIRunService(db).mark_disabled(run_id)
                db.commit()
        return "ai_disabled"

    if run_id is not None:
        with worker_db_session() as db:
            from app.services.ai_run import AIRunService

            AIRunService(db).mark_running(run_id, model=settings.LLM_MODEL_REASONING)
            db.commit()

    try:
        with worker_db_session() as db:
            asyncio.run(
                SolutionAdvisorService(db).generate_and_save(
                    issue_id,
                    actor_id=actor_id,
                    ip_address=ip_address,
                )
            )
            if run_id is not None:
                from app.services.ai_run import AIRunService

                AIRunService(db).mark_succeeded(run_id)
            db.commit()
        logger.info("worker.advise_issue.completed", issue_id=issue_id)
        return "ok"
    except Exception:
        logger.exception("worker.advise_issue.failed", issue_id=issue_id)
        if run_id is not None:
            try:
                with worker_db_session() as db:
                    from app.services.ai_run import AIRunService

                    AIRunService(db).mark_failed(run_id, error_code="provider_error")
                    db.commit()
            except Exception:
                pass
        return "failed"


def enqueue_advise_issue(
    issue_id: int,
    *,
    actor_id: int | None = None,
    ip_address: str | None = None,
    run_id: int | None = None,
) -> None:
    """Enqueue issue advice generation; no-op if broker unavailable."""
    try:
        advise_issue.delay(
            issue_id,
            actor_id=actor_id,
            ip_address=ip_address,
            run_id=run_id,
        )
    except Exception as exc:
        logger.warning("worker.enqueue_advise_failed", issue_id=issue_id, error=str(exc))


@celery_app.task(name="app.workers.tasks.generate_daily_project_summary")
def generate_daily_project_summary() -> str:
    """Generate daily summaries for all ACTIVE projects."""
    run_date = scheduler_today()
    if not acquire_daily_run_lock("generate_daily_project_summary", run_date):
        return "skipped_duplicate"
    settings = get_settings()
    if not settings.llm_configured:
        logger.info("worker.generate_daily_project_summary.ai_disabled")
        return "ai_disabled"
    try:
        with worker_db_session() as db:
            count = asyncio.run(DailySummaryService(db).generate_all_active(summary_date=run_date))
            db.commit()
    except Exception:
        logger.exception("worker.generate_daily_project_summary.failed")
        raise
    return f"generated:{count}"


@celery_app.task(
    name="app.workers.tasks.summarize_conversation",
    bind=True,
    max_retries=0,
)
def summarize_conversation(self: CeleryTask, conversation_id: int) -> str:
    """Refresh rolling conversation summary (Fast model)."""
    settings = get_settings()
    if not settings.llm_configured:
        logger.info(
            "worker.summarize_conversation.ai_disabled",
            conversation_id=conversation_id,
        )
        return "ai_disabled"
    try:
        with worker_db_session() as db:
            from app.services.conversation import ConversationService

            result = asyncio.run(ConversationService(db).refresh_summary(conversation_id))
            if result is None:
                return "not_found"
            db.commit()
        logger.info("worker.summarize_conversation.completed", conversation_id=conversation_id)
        return "ok"
    except Exception:
        logger.exception(
            "worker.summarize_conversation.failed",
            conversation_id=conversation_id,
        )
        return "failed"


def enqueue_conversation_summary(conversation_id: int) -> None:
    """Enqueue rolling summary; no-op if broker unavailable."""
    try:
        summarize_conversation.delay(conversation_id)
    except Exception as exc:
        logger.warning(
            "worker.enqueue_summary_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )


@celery_app.task(
    name="app.workers.tasks.generate_project_summary",
    bind=True,
    max_retries=0,
)
def generate_project_summary(
    self: CeleryTask,
    project_id: int,
    run_id: int | None = None,
) -> str:
    """Generate/refresh today's daily summary for one project."""
    settings = get_settings()
    if not settings.llm_configured:
        logger.info("worker.generate_project_summary.ai_disabled", project_id=project_id)
        if run_id is not None:
            with worker_db_session() as db:
                from app.services.ai_run import AIRunService

                AIRunService(db).mark_disabled(run_id)
                db.commit()
        return "ai_disabled"

    if run_id is not None:
        with worker_db_session() as db:
            from app.services.ai_run import AIRunService

            AIRunService(db).mark_running(run_id, model=settings.LLM_MODEL_FAST)
            db.commit()

    try:
        with worker_db_session() as db:
            asyncio.run(
                DailySummaryService(db).generate_for_project(
                    project_id,
                    skip_if_exists=False,
                )
            )
            if run_id is not None:
                from app.services.ai_run import AIRunService

                AIRunService(db).mark_succeeded(run_id)
            db.commit()
        return "ok"
    except Exception:
        logger.exception("worker.generate_project_summary.failed", project_id=project_id)
        if run_id is not None:
            try:
                with worker_db_session() as db:
                    from app.services.ai_run import AIRunService

                    AIRunService(db).mark_failed(run_id, error_code="provider_error")
                    db.commit()
            except Exception:
                pass
        return "failed"


def enqueue_generate_project_summary(project_id: int, *, run_id: int | None = None) -> None:
    try:
        generate_project_summary.delay(project_id, run_id=run_id)
    except Exception as exc:
        logger.warning(
            "worker.enqueue_project_summary_failed",
            project_id=project_id,
            error=str(exc),
        )
