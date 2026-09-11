"""Redis-backed idempotency for scheduled Celery jobs."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

import redis

from app.core.config import settings
from app.core.logging import get_logger
from app.workers.timezone import scheduler_today

logger = get_logger(__name__)

_LOCK_TTL_SECONDS = 60 * 60 * 48


@lru_cache
def _sync_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def daily_run_key(task_name: str, run_date: date) -> str:
    return f"celery:idem:{task_name}:{run_date.isoformat()}"


def acquire_daily_run_lock(task_name: str, run_date: date | None = None) -> bool:
    """Return True when this worker should execute the scheduled job for the day."""
    run_date = run_date or scheduler_today()
    key = daily_run_key(task_name, run_date)
    try:
        acquired = _sync_redis().set(key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully when Redis is down
        logger.warning("worker.idempotency.redis_unavailable", task=task_name, error=str(exc))
        return True
    if not acquired:
        logger.info(
            "worker.idempotency.skipped_duplicate",
            task=task_name,
            run_date=run_date.isoformat(),
        )
    return bool(acquired)


def release_daily_run_lock(task_name: str, run_date: date | None = None) -> None:
    """Remove a daily lock (mainly for tests)."""
    run_date = run_date or scheduler_today()
    try:
        _sync_redis().delete(daily_run_key(task_name, run_date))
    except Exception as exc:  # noqa: BLE001
        logger.warning("worker.idempotency.release_failed", task=task_name, error=str(exc))


def notification_once_key(dedupe_key: str) -> str:
    return f"notify:once:{dedupe_key}"


def claim_notification_once(dedupe_key: str, *, ttl_seconds: int = _LOCK_TTL_SECONDS) -> bool:
    """Claim a one-shot notification slot (NX). True means the caller should send.

    Used by daily reminder / missing-progress scans so a second Beat tick, manual
    re-run, or lock TTL edge cannot double-notify the same recipient for the same
    business day. Redis down → allow send (same degrade as daily job locks).
    """
    key = notification_once_key(dedupe_key)
    try:
        acquired = _sync_redis().set(key, "1", nx=True, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "worker.notify_once.redis_unavailable",
            dedupe_key=dedupe_key,
            error=str(exc),
        )
        return True
    if not acquired:
        logger.info("worker.notify_once.skipped_duplicate", dedupe_key=dedupe_key)
    return bool(acquired)


def release_notification_once(dedupe_key: str) -> None:
    """Drop a one-shot claim (tests)."""
    try:
        _sync_redis().delete(notification_once_key(dedupe_key))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "worker.notify_once.release_failed",
            dedupe_key=dedupe_key,
            error=str(exc),
        )