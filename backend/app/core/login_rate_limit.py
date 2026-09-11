"""Login brute-force throttle keyed by client IP + username."""

from __future__ import annotations

from functools import lru_cache

import redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "auth:login:rl:"


class LoginRateLimitExceeded(Exception):
    """Raised when login attempts exceed the configured window."""

    def __init__(self, *, retry_after: int) -> None:
        super().__init__("Too many login attempts. Try again later.")
        self.retry_after = max(1, retry_after)


@lru_cache
def _sync_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(ip_address: str | None, username: str) -> str:
    ip = (ip_address or "unknown").strip() or "unknown"
    user = username.strip().lower() or "unknown"
    return f"{_KEY_PREFIX}{ip}:{user}"


def assert_login_allowed(
    *,
    username: str,
    ip_address: str | None,
    settings: Settings | None = None,
) -> None:
    """Reject the request if this IP+username pair is already over the limit."""
    settings = settings or get_settings()
    limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
    if limit <= 0:
        return

    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    key = _key(ip_address, username)
    try:
        client = _sync_redis()
        raw = client.get(key)
        count = int(raw) if raw is not None else 0
        if count >= limit:
            ttl = int(client.ttl(key) or window)
            raise LoginRateLimitExceeded(retry_after=ttl if ttl > 0 else window)
    except LoginRateLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        logger.warning("auth.login_rate_limit_unavailable", error=str(exc))


def record_login_failure(
    *,
    username: str,
    ip_address: str | None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
    if limit <= 0:
        return

    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    key = _key(ip_address, username)
    try:
        client = _sync_redis()
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, window)
    except Exception as exc:  # noqa: BLE001
        logger.warning("auth.login_rate_limit_record_failed", error=str(exc))


def clear_login_attempts(
    *,
    username: str,
    ip_address: str | None,
) -> None:
    try:
        _sync_redis().delete(_key(ip_address, username))
    except Exception as exc:  # noqa: BLE001
        logger.warning("auth.login_rate_limit_clear_failed", error=str(exc))
