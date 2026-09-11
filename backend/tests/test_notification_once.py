"""Notification one-shot dedupe for daily scans."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.workers import idempotency


def test_claim_notification_once_is_idempotent():
    store: dict[str, str] = {}
    redis = MagicMock()

    def set_nx(key, value, nx=False, ex=None):  # noqa: ANN001
        if nx and key in store:
            return False
        store[key] = value
        return True

    redis.set.side_effect = set_nx
    redis.delete.side_effect = lambda key: store.pop(key, None)

    with patch.object(idempotency, "_sync_redis", return_value=redis):
        key = "TASK_REMINDER:9:2026-09-10"
        assert idempotency.claim_notification_once(key) is True
        assert idempotency.claim_notification_once(key) is False
        idempotency.release_notification_once(key)
        assert idempotency.claim_notification_once(key) is True


def test_claim_notification_once_allows_send_when_redis_down():
    redis = MagicMock()
    redis.set.side_effect = RuntimeError("redis down")
    with patch.object(idempotency, "_sync_redis", return_value=redis):
        assert idempotency.claim_notification_once("MISSING_PROGRESS:1:2026-09-10") is True
