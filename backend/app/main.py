"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import close_redis
from app.services.schedule_guard import ScheduleImpactRequiresProposal

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info(
        "app.startup",
        environment=settings.ENVIRONMENT,
        llm_configured=settings.llm_configured,
        wecom_configured=settings.wecom_configured,
    )
    yield
    await close_redis()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    configure_logging()
    docs_url = "/docs" if settings.openapi_enabled else None
    redoc_url = "/redoc" if settings.openapi_enabled else None
    openapi_url = "/openapi.json" if settings.openapi_enabled else None
    app = FastAPI(
        title="AI 项目管理 Agent API",
        description="AI-assisted project tracking across industries.",
        version=settings.APP_VERSION,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    if settings.CORS_ORIGINS or settings.cors_allow_lan:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS or [],
            allow_origin_regex=(
                settings.cors_lan_origin_regex if settings.cors_allow_lan else None
            ),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(ScheduleImpactRequiresProposal)
    async def _schedule_impact(
        request: Request, exc: ScheduleImpactRequiresProposal
    ) -> JSONResponse:
        """Refused because the edit would move other tasks; tell the UI what and where."""
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": exc.message,
                "code": "SCHEDULE_IMPACT_REQUIRES_PROPOSAL",
                "action": exc.action,
                "impacted_tasks": jsonable_encoder(exc.impacted),
            },
        )

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
