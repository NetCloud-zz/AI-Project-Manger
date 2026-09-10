"""Auth provider registry."""

from __future__ import annotations

from app.core.auth.local import LocalAuthProvider
from app.core.auth.provider import AuthProvider
from app.core.auth.wecom import WeComAuthProvider

PROVIDERS: dict[str, AuthProvider] = {
    LocalAuthProvider.name: LocalAuthProvider(),
    WeComAuthProvider.name: WeComAuthProvider(),
}


def get_auth_provider(name: str = "local") -> AuthProvider:
    provider = PROVIDERS.get(name)
    if provider is None:
        msg = f"Unknown auth provider: {name}"
        raise ValueError(msg)
    return provider
