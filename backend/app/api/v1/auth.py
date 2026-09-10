"""Authentication routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_client_ip
from app.integrations.wecom.client import WeComClient
from app.integrations.wecom.exceptions import WeComNotConfiguredError, WeComOAuthStateError
from app.integrations.wecom.oauth_state import WeComOAuthStateStore
from app.schemas.auth import LoginRequest, LoginResponse
from app.schemas.user import UserResponse
from app.services.auth import (
    AuthenticationError,
    AuthService,
    OaAuthenticationError,
    WeComAuthenticationError,
)

router = APIRouter(prefix="/auth", tags=["auth"])
_oauth_state_store = WeComOAuthStateStore()


@router.post("/login", response_model=LoginResponse, summary="Login with username and password")
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    auth_service = AuthService(db)
    try:
        token, user = auth_service.login(
            username=body.username,
            password=body.password,
            ip_address=get_client_ip(request),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    db.commit()
    current_settings = get_settings()
    return LoginResponse(
        access_token=token,
        expires_in=current_settings.JWT_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.get("/wecom/login", summary="Start WeCom OAuth login")
def wecom_login() -> RedirectResponse:
    current_settings = get_settings()
    if not current_settings.wecom_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WeCom is not configured",
        )
    try:
        client = WeComClient(current_settings)
        state = _oauth_state_store.issue_state()
        authorize_url = client.build_oauth_authorize_url(state=state)
    except WeComNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/wecom/callback", summary="WeCom OAuth callback")
def wecom_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> RedirectResponse:
    current_settings = get_settings()
    if not current_settings.wecom_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WeCom is not configured",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    try:
        _oauth_state_store.validate_and_consume(state)
    except WeComOAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    auth_service = AuthService(db)
    try:
        token, _user = auth_service.login_with_wecom(
            code=code,
            ip_address=get_client_ip(request),
        )
    except WeComAuthenticationError as exc:
        db.commit()
        params = urlencode({"error": str(exc)})
        return RedirectResponse(
            url=f"{current_settings.frontend_base_url}/auth/wecom/callback?{params}",
            status_code=status.HTTP_302_FOUND,
        )

    db.commit()
    params = urlencode(
        {
            "access_token": token,
            "expires_in": current_settings.JWT_EXPIRE_MINUTES * 60,
        }
    )
    return RedirectResponse(
        url=f"{current_settings.frontend_base_url}/auth/wecom/callback?{params}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/oa/sso", summary="OA signed SSO jump (HMAC ticket)")
def oa_sso(
    request: Request,
    db: Session = Depends(get_db),
    uid: int = Query(..., description="OA osri_admin.id"),
    ts: int = Query(..., description="Unix timestamp when the ticket was issued"),
    sign: str = Query(..., description="HMAC-SHA256 hex of '{uid}|{ts}'"),
) -> RedirectResponse:
    """Validate OA jump ticket, JIT-provision local user, redirect with JWT.

    OA menu URL example (PHP on OA side must generate ``sign`` with ``OA_SSO_SECRET``)::

        /api/v1/auth/oa/sso?uid={adminid}&ts={time()}&sign={hmac}
    """
    current_settings = get_settings()
    if not current_settings.oa_sso_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OA SSO is not configured",
        )

    auth_service = AuthService(db)
    try:
        token, _user = auth_service.login_with_oa_sso(
            uid=uid,
            ts=ts,
            sign=sign,
            ip_address=get_client_ip(request),
        )
    except OaAuthenticationError as exc:
        db.commit()
        params = urlencode({"error": str(exc)})
        return RedirectResponse(
            url=f"{current_settings.frontend_base_url}/auth/oa/callback?{params}",
            status_code=status.HTTP_302_FOUND,
        )

    db.commit()
    params = urlencode(
        {
            "access_token": token,
            "expires_in": current_settings.JWT_EXPIRE_MINUTES * 60,
        }
    )
    return RedirectResponse(
        url=f"{current_settings.frontend_base_url}/auth/oa/callback?{params}",
        status_code=status.HTTP_302_FOUND,
    )
