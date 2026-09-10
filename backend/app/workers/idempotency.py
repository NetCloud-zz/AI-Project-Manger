"""Redis-backed idempotency for scheduled Celery jobs."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

import redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LOCK_TTL_SECONDS = 60 * 60 * 48


@lru_cache
def _sync_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def daily_run_key(task_name: str, run_date: date) -> str:
    return f"celery:idem:{task_name}:{run_date.isoformat()}"


def acquire_daily_run_lock(task_name: str, run_date: date | None = None) -> bool:
    """Return True when this worker should execute the scheduled job for the day."""
    run_date = run_date or date.today()
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
    run_date = run_date or date.today()
    try:
        _sync_redis().delete(daily_run_key(task_name, run_date))
    except Exception as exc:  # noqa: BLE001
        logger.warning("worker.idempotency.release_failed", task=task_name, error=str(exc))
