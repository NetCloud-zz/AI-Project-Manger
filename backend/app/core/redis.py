"""Redis client used for caching, rate limiting and as the Celery broker."""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis, from_url

from app.core.config import settings


@lru_cache
def get_redis() -> Redis:
    """Return the process wide Redis client (lazily connected)."""
    return from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )


async def check_redis() -> None:
    """Raise if Redis is unreachable. Used by the readiness probe."""
    await get_redis().ping()


async def close_redis() -> None:
    """Release connections on application shutdown."""
    await get_redis().aclose()
    get_redis.cache_clear()
