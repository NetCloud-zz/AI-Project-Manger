"""Unified application configuration.

All runtime configuration is read from environment variables (or a local `.env`
file) exactly once and exposed through the cached :func:`get_settings` accessor.

External integrations (LLM gateway, WeCom) are intentionally optional: the
application must boot successfully without their credentials so that development
never blocks on missing secrets.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "dev", "staging", "prod"]
LogFormat = Literal["console", "json"]

# Known placeholders that must never be used as a real signing key.
INSECURE_JWT_SECRETS = frozenset(
    {
        "change-me-in-production",
        "changeme",
        "change-me",
        "secret",
        "jwt-secret",
        "your-secret-here",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    APP_NAME: str = "project-agent"
    APP_VERSION: str = "0.2.2"
    ENVIRONMENT: Environment = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    # None = auto (enabled only when ENVIRONMENT=local). Explicit true/false wins.
    OPENAPI_ENABLED: bool | None = None

    # --- Logging ---
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: LogFormat = "console"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg://project_agent:project_agent@localhost:5432/project_agent"
    )
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Celery ---
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    SCHEDULER_TIMEZONE: str = "Asia/Shanghai"
    # Calendar-day logic (due dates, overdue, “today”) uses this timezone.
    # Falls back to SCHEDULER_TIMEZONE when unset.
    BUSINESS_TZ: str | None = None
    DAILY_TASK_SCAN_HOUR: int = 9
    MISSING_PROGRESS_SCAN_HOUR: int = 15
    DAILY_SUMMARY_HOUR: int = 18
    RISK_SCAN_HOUR: int = 8
    AI_RISK_EVIDENCE_MAX_AGE_DAYS: int = Field(default=7, ge=1, le=365)

    # --- Plan change notification outbox (S4) ---
    NOTIFICATION_DISPATCH_INTERVAL_SECONDS: int = Field(default=60, ge=10, le=3600)
    NOTIFICATION_DISPATCH_BATCH: int = Field(default=50, ge=1, le=500)
    NOTIFICATION_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    NOTIFICATION_RETRY_BACKOFF_SECONDS: int = Field(default=60, ge=5, le=3600)

    # --- Auth ---
    # Default is intentionally insecure so misconfigured deploys fail the
    # model_validator below instead of silently shipping a forgeable key.
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 12
    # Local-only escape hatch for throwaway sandboxes. Never set in shared/prod.
    ALLOW_INSECURE_JWT: bool = False
    # Login brute-force throttle (IP + username). 0 disables.
    LOGIN_RATE_LIMIT_ATTEMPTS: int = Field(default=10, ge=0, le=1000)
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=300, ge=30, le=86400)
    # Allow seed script to use documented demo passwords (local only).
    ALLOW_PUBLIC_SEED_PASSWORDS: bool = False

    # --- CORS ---
    # NoDecode keeps pydantic-settings from JSON-parsing the raw value so the
    # validator below can accept a plain comma separated list.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    # In local/dev, also allow browser origins on private LAN IPs (any port).
    CORS_ALLOW_LAN: bool = False

    # --- LLM gateway (optional) ---
    LLM_BASE_URL: str | None = None
    LLM_API_KEY: str | None = None
    LLM_MODEL_FAST: str = "qwen-plus"
    LLM_MODEL_REASONING: str = "deepseek-v3"
    # Large pastes / 1M-context models need more than a minute end-to-end.
    LLM_TIMEOUT_SECONDS: int = 300

    # --- Project Assistant context (PHASE B) ---
    # Recent completed turns fed to the model (user+assistant pairs count as 2).
    AGENT_RECENT_MESSAGES: int = 200
    # Soft budget; chars/2 is a coarse token estimate (CN+EN mix).
    # Default matches 1M-context models; override via env if the provider is smaller.
    AGENT_MAX_CONTEXT_TOKENS: int = 1_000_000
    # Rolling summary kicks in after this many stored messages (async, fast model).
    AGENT_SUMMARY_TRIGGER_MESSAGES: int = 40
    # Project Assistant ReAct runtime. ``legacy`` keeps the in-house tool loop.
    AGENT_RUNTIME: Literal["agentscope", "legacy"] = "agentscope"
    # LLM turns vs per-operation parameter retries. Do not collapse these into one cap.
    AGENT_REASONING_ROUNDS: int = Field(default=20, ge=1, le=50)
    AGENT_TOOL_CORRECTION_ROUNDS: int = Field(default=10, ge=1, le=20)

    # --- WeCom (optional) ---
    WECOM_CORP_ID: str | None = None
    WECOM_AGENT_ID: str | None = None
    WECOM_SECRET: str | None = None
    WECOM_REDIRECT_URL: str | None = None
    FRONTEND_BASE_URL: str | None = None

    # --- OA MySQL directory + SSO (optional, read-only against OA) ---
    # RockOA table is typically `{prefix}_admin` (here: osri_admin), not bare `admin`.
    OA_MYSQL_HOST: str | None = None
    OA_MYSQL_PORT: int = 3306
    OA_MYSQL_USER: str | None = None
    OA_MYSQL_PASSWORD: str | None = None
    OA_MYSQL_DATABASE: str | None = None
    OA_MYSQL_ADMIN_TABLE: str = "osri_admin"
    OA_SSO_SECRET: str | None = None
    OA_SSO_MAX_AGE_SECONDS: int = 300
    OA_BASE_URL: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept either a comma separated string or a JSON array."""
        if not isinstance(value, str):
            return value
        raw = value.strip()
        if raw.startswith("["):
            return json.loads(raw)
        return [item.strip() for item in raw.split(",") if item.strip()]

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator(
        "DAILY_TASK_SCAN_HOUR",
        "MISSING_PROGRESS_SCAN_HOUR",
        "DAILY_SUMMARY_HOUR",
        "RISK_SCAN_HOUR",
        mode="before",
    )
    @classmethod
    def _validate_scheduler_hour(cls, value: object) -> object:
        if isinstance(value, str):
            value = int(value.strip())
        if not isinstance(value, int) or value < 0 or value > 23:
            msg = "Scheduler hour must be an integer between 0 and 23"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _reject_insecure_jwt_secret(self) -> Self:
        secret = (self.JWT_SECRET or "").strip()
        insecure = secret in INSECURE_JWT_SECRETS or len(secret) < 32
        if not insecure:
            return self
        if self.ENVIRONMENT == "local" and self.ALLOW_INSECURE_JWT:
            return self
        raise ValueError(
            "JWT_SECRET is missing, shorter than 32 characters, or a known "
            "insecure default. Generate one with `openssl rand -hex 32`. "
            "Local sandboxes only: set ALLOW_INSECURE_JWT=true."
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def llm_configured(self) -> bool:
        """Whether a real LLM gateway is reachable; otherwise a stub is used."""
        return bool(self.LLM_BASE_URL and self.LLM_API_KEY)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wecom_configured(self) -> bool:
        """Whether WeCom credentials exist; otherwise notifications go to console."""
        return bool(self.WECOM_CORP_ID and self.WECOM_AGENT_ID and self.WECOM_SECRET)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oa_mysql_configured(self) -> bool:
        """Whether OA MySQL directory credentials are present (read-only use)."""
        return bool(
            self.OA_MYSQL_HOST
            and self.OA_MYSQL_USER
            and self.OA_MYSQL_PASSWORD
            and self.OA_MYSQL_DATABASE
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oa_sso_configured(self) -> bool:
        """SSO needs MySQL lookup + shared HMAC secret."""
        return self.oa_mysql_configured and bool(self.OA_SSO_SECRET)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def frontend_base_url(self) -> str:
        """Public frontend URL used in WeCom H5 message links."""
        if self.FRONTEND_BASE_URL:
            return self.FRONTEND_BASE_URL.rstrip("/")
        if self.CORS_ORIGINS:
            return self.CORS_ORIGINS[0].rstrip("/")
        return "http://localhost:3000"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_allow_lan(self) -> bool:
        """Non-prod stacks allow LAN dev clients; prod requires explicit opt-in."""
        return self.ENVIRONMENT != "prod" or self.CORS_ALLOW_LAN

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_lan_origin_regex(self) -> str:
        return (
            r"https?://("
            r"localhost|127\.0\.0\.1|"
            r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"192\.168\.\d{1,3}\.\d{1,3}|"
            r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
            r")(?::\d+)?"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "prod"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def openapi_enabled(self) -> bool:
        """Swagger/OpenAPI are local-dev aids; keep them off on shared stacks."""
        if self.OPENAPI_ENABLED is not None:
            return self.OPENAPI_ENABLED
        return self.ENVIRONMENT == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
