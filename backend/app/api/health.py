"""Liveness and readiness endpoints.

`/health` stays dependency free so container orchestration can tell the process
apart from its backing services. `/health/ready` actually probes PostgreSQL and
Redis and reports 503 when a required dependency is down.
"""

from __future__ import annotations

import anyio
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.database import check_database
from app.core.logging import get_logger
from app.core.redis import check_redis
from app.schemas.health import DependencyHealth, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(response: Response) -> ReadinessResponse:
    dependencies: dict[str, DependencyHealth] = {}

    try:
        await anyio.to_thread.run_sync(check_database)
        dependencies["postgres"] = DependencyHealth(status="up")
    except Exception as exc:  # noqa: BLE001 - report any driver level failure
        logger.warning("readiness.postgres_unavailable", error=str(exc))
        dependencies["postgres"] = DependencyHealth(status="down", detail=str(exc))

    try:
        await check_redis()
        dependencies["redis"] = DependencyHealth(status="up")
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness.redis_unavailable", error=str(exc))
        dependencies["redis"] = DependencyHealth(status="down", detail=str(exc))

    # Optional integrations never make the service unhealthy.
    dependencies["llm"] = DependencyHealth(
        status="up" if settings.llm_configured else "not_configured",
        detail=None
        if settings.llm_configured
        else "LLM_BASE_URL/LLM_API_KEY absent, stub provider in use",
    )
    dependencies["wecom"] = DependencyHealth(
        status="up" if settings.wecom_configured else "not_configured",
        detail=None
        if settings.wecom_configured
        else "WeCom credentials absent, console provider in use",
    )
    if settings.oa_mysql_configured:
        try:
            from app.integrations.oa.client import OaMySQLClient

            await anyio.to_thread.run_sync(OaMySQLClient(settings).ping)
            dependencies["oa_mysql"] = DependencyHealth(status="up")
        except Exception as exc:  # noqa: BLE001
            logger.warning("readiness.oa_mysql_unavailable", error=str(exc))
            dependencies["oa_mysql"] = DependencyHealth(
                status="down",
                detail=str(exc),
            )
    else:
        dependencies["oa_mysql"] = DependencyHealth(
            status="not_configured",
            detail="OA MySQL credentials absent",
        )
    dependencies["oa_sso"] = DependencyHealth(
        status="up" if settings.oa_sso_configured else "not_configured",
        detail=None if settings.oa_sso_configured else "OA_SSO_SECRET or OA MySQL absent",
    )

    required_down = any(dependencies[name].status == "down" for name in ("postgres", "redis"))
    if required_down:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="degraded" if required_down else "ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        dependencies=dependencies,
    )
