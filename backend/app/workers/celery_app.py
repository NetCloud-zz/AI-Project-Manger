"""Celery application used for background work and scheduled tracking jobs."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings, settings
from app.core.logging import configure_logging

configure_logging()


def build_beat_schedule() -> dict[str, dict]:
    """Build Beat schedule from configurable scheduler hours."""
    cfg = get_settings()
    return {
        "scan-daily-tasks": {
            "task": "app.workers.tasks.scan_daily_tasks",
            "schedule": crontab(hour=cfg.DAILY_TASK_SCAN_HOUR, minute=0),
        },
        "scan-missing-progress": {
            "task": "app.workers.tasks.scan_missing_progress",
            "schedule": crontab(hour=cfg.MISSING_PROGRESS_SCAN_HOUR, minute=0),
        },
        "scan-risk": {
            "task": "app.workers.tasks.scan_risk",
            "schedule": crontab(hour=cfg.RISK_SCAN_HOUR, minute=0),
        },
        "generate-daily-project-summary": {
            "task": "app.workers.tasks.generate_daily_project_summary",
            "schedule": crontab(hour=cfg.DAILY_SUMMARY_HOUR, minute=0),
        },
        # Compensating sweep; applying a change also enqueues delivery directly.
        "dispatch-plan-notifications": {
            "task": "app.workers.tasks.dispatch_plan_notifications",
            "schedule": float(cfg.NOTIFICATION_DISPATCH_INTERVAL_SECONDS),
        },
    }


celery_app = Celery(
    settings.APP_NAME,
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.SCHEDULER_TIMEZONE,
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_max_retries=0,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
    result_expires=60 * 60 * 24,
)

celery_app.conf.beat_schedule = build_beat_schedule()
