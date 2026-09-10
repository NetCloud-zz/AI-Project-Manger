"""Password hashing and JWT helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings, get_settings

# Keys that must never appear in audit payloads or API responses.
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "password_hash",
        "hashed_password",
        "jwt_secret",
        "secret",
        "api_key",
        "llm_api_key",
        "token",
        "access_token",
        "refresh_token",
    }
)


def hash_password(plain_password: str) -> str:
    digest = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(
    *,
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "type": "access"}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        msg = "Invalid token type"
        raise jwt.InvalidTokenError(msg)
    return payload


def sanitize_for_audit(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip sensitive keys before writing an audit record."""
    if data is None:
        return None
    return {key: value for key, value in data.items() if key.lower() not in SENSITIVE_FIELD_NAMES}


def sanitize_log_values(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive keys before emitting structured logs."""
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in SENSITIVE_FIELD_NAMES:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = sanitize_log_values(value)
        else:
            redacted[key] = value
    return redacted
