"""Authentication business logic."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth import get_auth_provider
from app.core.auth.provider import AuthCredentials, AuthProviderNotConfiguredError
from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.integrations.oa.client import OaMySQLClient
from app.integrations.oa.exceptions import (
    OaNotConfiguredError,
    OaSsoError,
    OaUserNotFoundError,
)
from app.integrations.oa.sso import verify_sso_sign
from app.integrations.oa.sso_ticket_store import consume_sso_ticket
from app.integrations.wecom.exceptions import WeComUserMappingError
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.audit import AuditService
from app.services.user import UserService


class AuthenticationError(Exception):
    """Raised when credentials are invalid or the account is inactive."""


class WeComAuthenticationError(AuthenticationError):
    """Raised when WeCom login fails for a mapped-user or configuration reason."""

    def __init__(self, message: str, *, wechat_user_id: str | None = None) -> None:
        super().__init__(message)
        self.wechat_user_id = wechat_user_id


class OaAuthenticationError(AuthenticationError):
    """Raised when OA SSO fails."""

    def __init__(self, message: str, *, oa_admin_id: int | None = None) -> None:
        super().__init__(message)
        self.oa_admin_id = oa_admin_id


class AuthService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.audit = AuditService(db)
        self.provider = get_auth_provider("local")

    def login(
        self,
        *,
        username: str,
        password: str,
        ip_address: str | None = None,
    ) -> tuple[str, User]:
        result = self.provider.authenticate(
            self.db,
            AuthCredentials(username=username, password=password),
        )
        if result is None:
            self.audit.record(
                action="auth.login_failed",
                resource_type="user",
                resource_id=username,
                ip_address=ip_address,
                new_value={"username": username, "provider": self.provider.name},
            )
            raise AuthenticationError("Invalid username or password")

        user = result.user
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value, "username": user.username},
            settings=self.settings,
        )
        self.audit.record(
            action="auth.login_success",
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=ip_address,
            new_value={"provider": result.provider, "username": user.username},
        )
        return token, user

    def login_with_wecom(
        self,
        *,
        code: str,
        ip_address: str | None = None,
    ) -> tuple[str, User]:
        provider = get_auth_provider("wecom")
        try:
            result = provider.authenticate(
                self.db,
                AuthCredentials(wecom_code=code),
            )
        except AuthProviderNotConfiguredError as exc:
            raise WeComAuthenticationError(str(exc)) from exc
        except WeComUserMappingError as exc:
            self.audit.record(
                action="auth.wecom_login_failed",
                resource_type="user",
                resource_id=exc.wechat_user_id,
                ip_address=ip_address,
                new_value={
                    "provider": "wecom",
                    "reason": "user_not_mapped",
                    "wechat_user_id": exc.wechat_user_id,
                },
            )
            raise WeComAuthenticationError(
                "WeCom account is not linked to an active system user. "
                "Ask an administrator to set wechat_user_id on your profile.",
                wechat_user_id=exc.wechat_user_id,
            ) from exc

        if result is None:
            raise WeComAuthenticationError("Invalid WeCom authorization code")

        user = result.user
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value, "username": user.username},
            settings=self.settings,
        )
        self.audit.record(
            action="auth.login_success",
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=ip_address,
            new_value={
                "provider": result.provider,
                "username": user.username,
                "wechat_user_id": user.wechat_user_id,
            },
        )
        return token, user

    def login_with_oa_sso(
        self,
        *,
        uid: int,
        ts: int,
        sign: str,
        ip_address: str | None = None,
    ) -> tuple[str, User]:
        if not self.settings.oa_sso_configured:
            raise OaAuthenticationError("OA SSO is not configured")

        try:
            verify_sso_sign(
                uid=uid,
                ts=ts,
                sign=sign,
                secret=self.settings.OA_SSO_SECRET or "",
                max_age_seconds=self.settings.OA_SSO_MAX_AGE_SECONDS,
            )
            # TTL covers the full skew window so a ticket cannot be replayed
            # until it would already be rejected as expired.
            consume_sso_ticket(
                uid=uid,
                ts=ts,
                sign=sign,
                ttl_seconds=self.settings.OA_SSO_MAX_AGE_SECONDS,
            )
        except OaSsoError as exc:
            self.audit.record(
                action="auth.oa_sso_failed",
                resource_type="oa_admin",
                resource_id=str(uid),
                ip_address=ip_address,
                new_value={"provider": "oa", "reason": "bad_ticket", "detail": str(exc)},
            )
            raise OaAuthenticationError(str(exc), oa_admin_id=uid) from exc

        try:
            record = OaMySQLClient(self.settings).get_active_by_id(uid)
        except OaNotConfiguredError as exc:
            raise OaAuthenticationError(str(exc), oa_admin_id=uid) from exc
        except OaUserNotFoundError as exc:
            self.audit.record(
                action="auth.oa_sso_failed",
                resource_type="oa_admin",
                resource_id=str(uid),
                ip_address=ip_address,
                new_value={"provider": "oa", "reason": "user_not_active"},
            )
            raise OaAuthenticationError(
                "OA user not found or inactive",
                oa_admin_id=uid,
            ) from exc

        user_service = UserService(self.db, self.settings)
        user, _created = user_service.ensure_user_from_oa(
            record,
            ip_address=ip_address,
        )
        if not user.is_active:
            raise OaAuthenticationError("Local user account is inactive", oa_admin_id=uid)

        token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value, "username": user.username},
            settings=self.settings,
        )
        self.audit.record(
            action="auth.login_success",
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=ip_address,
            new_value={
                "provider": "oa",
                "username": user.username,
                "oa_admin_id": user.oa_admin_id,
            },
        )
        return token, user

    def get_user_from_token(self, token: str) -> User:
        from app.core.security import decode_access_token

        try:
            payload = decode_access_token(token, self.settings)
        except Exception as exc:
            msg = "Invalid or expired token"
            raise AuthenticationError(msg) from exc

        user_id = payload.get("sub")
        if user_id is None:
            raise AuthenticationError("Invalid token payload")

        user = self.users.get_by_id(int(user_id))
        if user is None or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        return user
