"""JWT helpers and insecure-secret rejection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_JWT_SECRETS, Settings
from app.core.security import create_access_token, decode_access_token


def test_create_and_decode_access_token_roundtrip():
    settings = Settings(
        JWT_SECRET="stage5-test-secret-key-32bytes-min!",
        ENVIRONMENT="local",
        ALLOW_INSECURE_JWT=True,
    )
    token = create_access_token(
        subject="42",
        extra_claims={"role": "ADMIN", "username": "tester"},
        settings=settings,
    )
    payload = decode_access_token(token, settings=settings)
    assert payload["sub"] == "42"
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"


@pytest.mark.parametrize("secret", sorted(INSECURE_JWT_SECRETS)[:3] + ["short"])
def test_insecure_jwt_secret_rejected_outside_local_bypass(secret: str):
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET=secret, ENVIRONMENT="prod", ALLOW_INSECURE_JWT=False)
