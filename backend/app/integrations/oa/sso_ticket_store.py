"""One-time OA SSO ticket consumption (anti-replay)."""

from __future__ import annotations

import hashlib
from functools import lru_cache

import redis

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.oa.exceptions import OaSsoError

logger = get_logger(__name__)

_KEY_PREFIX = "oa:sso:ticket:"


@lru_cache
def _sync_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def consume_sso_ticket(
    *,
    uid: int,
    ts: int,
    sign: str,
    ttl_seconds: int,
) -> None:
    """Mark a validated SSO ticket as used. Raises if replayed or store is down.

    Key includes uid, ts and a digest of the signature so the same ticket cannot
    be reused within its validity window.
    """
    if ttl_seconds <= 0:
        raise OaSsoError("Invalid SSO ticket TTL")

    digest = hashlib.sha256(sign.strip().lower().encode("utf-8")).hexdigest()[:32]
    key = f"{_KEY_PREFIX}{uid}:{ts}:{digest}"
    try:
        created = _sync_redis().set(key, "1", nx=True, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.error("oa.sso.ticket_store_unavailable", error=str(exc))
        raise OaSsoError("SSO ticket store unavailable") from exc

    if not created:
        raise OaSsoError("SSO ticket already used")
