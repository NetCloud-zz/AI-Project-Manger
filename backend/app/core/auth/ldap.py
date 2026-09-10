"""LDAP / Active Directory provider stub."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth.provider import (
    AuthCredentials,
    AuthProvider,
    AuthResult,
)


class LDAPAuthProvider(AuthProvider):
    name = "ldap"

    def authenticate(self, db: Session, credentials: AuthCredentials) -> AuthResult | None:
        if not credentials.ldap_username:
            return None
        msg = "LDAPAuthProvider is not implemented yet"
        raise NotImplementedError(msg)


class SSOAuthProvider(AuthProvider):
    name = "sso"

    def authenticate(self, db: Session, credentials: AuthCredentials) -> AuthResult | None:
        if not credentials.sso_token:
            return None
        msg = "SSOAuthProvider is not implemented yet"
        raise NotImplementedError(msg)
