"""OAuth CSRF state storage for WeCom login."""

from __future__ import annotations

import secrets
from functools import lru_cache

import redis

from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.wecom.exceptions import WeComOAuthStateError

logger = get_logger(__name__)

_STATE_TTL_SECONDS = 600
_STATE_KEY_PREFIX = "wecom:oauth:state:"


@lru_cache
def _sync_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


class WeComOAuthStateStore:
    """Issue and validate one-time OAuth state tokens."""

    def issue_state(self) -> str:
        state = secrets.token_urlsafe(32)
        key = f"{_STATE_KEY_PREFIX}{state}"
        try:
            _sync_redis().set(key, "1", ex=_STATE_TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001 - degrade for local dev
            logger.warning("wecom.oauth.state_store_unavailable", error=str(exc))
            _memory_states.add(state)
        return state

    def validate_and_consume(self, state: str | None) -> None:
        if not state:
            raise WeComOAuthStateError("Missing OAuth state")
        key = f"{_STATE_KEY_PREFIX}{state}"
        try:
            deleted = _sync_redis().delete(key)
            if deleted:
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("wecom.oauth.state_validate_redis_unavailable", error=str(exc))
            if state in _memory_states:
                _memory_states.discard(state)
                return
        raise WeComOAuthStateError("Invalid or expired OAuth state")


_memory_states: set[str] = set()


def clear_oauth_state_memory() -> None:
    """Clear in-memory OAuth states (for tests)."""
    _memory_states.clear()
