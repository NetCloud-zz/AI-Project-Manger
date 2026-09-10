"""Username + password authentication."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth.provider import AuthCredentials, AuthProvider, AuthResult
from app.core.security import verify_password
from app.models.user import User, UserStatus


class LocalAuthProvider(AuthProvider):
    name = "local"

    def authenticate(self, db: Session, credentials: AuthCredentials) -> AuthResult | None:
        if not credentials.username or not credentials.password:
            return None

        user = db.scalar(select(User).where(User.username == credentials.username))
        if user is None or user.status != UserStatus.ACTIVE:
            return None
        if not verify_password(credentials.password, user.password_hash):
            return None
        return AuthResult(user=user, provider=self.name)
