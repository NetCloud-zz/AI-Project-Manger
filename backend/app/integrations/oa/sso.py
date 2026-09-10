"""HMAC ticket helpers for OA → project-agent SSO."""

from __future__ import annotations

import hashlib
import hmac
import time

from app.integrations.oa.exceptions import OaSsoError


def build_sso_sign(*, uid: int, ts: int, secret: str) -> str:
    """Return hex HMAC-SHA256 over ``{uid}|{ts}``."""
    payload = f"{uid}|{ts}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_sso_sign(
    *,
    uid: int,
    ts: int,
    sign: str,
    secret: str,
    max_age_seconds: int,
    now: int | None = None,
) -> None:
    """Validate SSO parameters or raise :class:`OaSsoError`."""
    if not secret:
        raise OaSsoError("OA SSO secret is not configured")
    if uid <= 0:
        raise OaSsoError("Invalid OA user id")
    if not sign or len(sign) > 128:
        raise OaSsoError("Invalid SSO signature")

    current = now if now is not None else int(time.time())
    if ts <= 0 or abs(current - ts) > max_age_seconds:
        raise OaSsoError("SSO ticket expired or timestamp invalid")

    expected = build_sso_sign(uid=uid, ts=ts, secret=secret)
    if not hmac.compare_digest(expected.lower(), sign.strip().lower()):
        raise OaSsoError("SSO signature mismatch")
