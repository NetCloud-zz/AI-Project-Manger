"""Opt-in Redis readiness for acceptance environments."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("REDIS_TESTS") != "1", reason="Opt-in Redis acceptance"
)


@pytest.mark.asyncio
async def test_redis_ping():
    from app.core.redis import check_redis, close_redis

    await check_redis()
    await close_redis()
