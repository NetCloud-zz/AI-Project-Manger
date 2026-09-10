"""WeCom OAuth authentication provider."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth.provider import (
    AuthCredentials,
    AuthProvider,
    AuthProviderNotConfiguredError,
    AuthResult,
)
from app.core.config import get_settings
from app.integrations.wecom.client import WeComClient
from app.integrations.wecom.exceptions import WeComUserMappingError
from app.models.user import User, UserStatus


class WeComAuthProvider(AuthProvider):
    name = "wecom"

    def __init__(self, client: WeComClient | None = None) -> None:
        self._client = client

    def authenticate(self, db: Session, credentials: AuthCredentials) -> AuthResult | None:
        settings = get_settings()
        if not settings.wecom_configured:
            raise AuthProviderNotConfiguredError("WeCom credentials are not configured")
        if not credentials.wecom_code:
            return None

        client = self._client or WeComClient(settings)
        wechat_user_id = client.get_user_id_by_code(credentials.wecom_code)
        user = db.scalar(
            select(User).where(
                User.wechat_user_id == wechat_user_id,
                User.status == UserStatus.ACTIVE,
            )
        )
        if user is None:
            raise WeComUserMappingError(wechat_user_id)
        return AuthResult(user=user, provider=self.name)
