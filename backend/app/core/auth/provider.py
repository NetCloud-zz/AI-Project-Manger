"""Authentication provider abstraction.

Each provider encapsulates one identity source (local password, WeCom OAuth,
LDAP, enterprise SSO). The application selects the active provider from
configuration; unconfigured external providers remain as stubs that raise
``NotImplementedError`` so the service can boot without their credentials.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.user import User


@dataclass(frozen=True, slots=True)
class AuthCredentials:
    """Provider-specific credential payload."""

    username: str | None = None
    password: str | None = None
    wecom_code: str | None = None
    ldap_username: str | None = None
    sso_token: str | None = None


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    provider: str


class AuthProvider(ABC):
    name: str

    @abstractmethod
    def authenticate(self, db: Session, credentials: AuthCredentials) -> AuthResult | None:
        """Return an authenticated user, or ``None`` when credentials are invalid."""


class AuthProviderNotConfiguredError(RuntimeError):
    """Raised when an external provider is invoked without credentials."""
