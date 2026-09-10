"""WeCom HTTP client with access-token caching."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.wecom.exceptions import WeComAPIError, WeComNotConfiguredError
from app.integrations.wecom.schemas import (
    WeComSendMessageResponse,
    WeComTokenResponse,
    WeComUserInfoResponse,
)

logger = get_logger(__name__)

WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
WECOM_OAUTH_BASE = "https://open.weixin.qq.com/connect/oauth2/authorize"
_TOKEN_REFRESH_BUFFER_SECONDS = 120


@dataclass(slots=True)
class _CachedAccessToken:
    token: str
    expires_at: float


_token_cache: dict[str, _CachedAccessToken] = {}


def clear_token_cache() -> None:
    """Clear cached access tokens (for tests)."""
    _token_cache.clear()


class WeComClient:
    """Low-level WeCom API client."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._http = http_client or httpx.Client(timeout=15.0)

    def _require_configured(self) -> None:
        if not self._settings.wecom_configured:
            raise WeComNotConfiguredError("WeCom credentials are not configured")

    def _cache_key(self) -> str:
        assert self._settings.WECOM_CORP_ID is not None
        assert self._settings.WECOM_SECRET is not None
        return f"{self._settings.WECOM_CORP_ID}:{self._settings.WECOM_SECRET}"

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        """Return a cached access token, refreshing when near expiry."""
        self._require_configured()
        key = self._cache_key()
        now = time.time()
        cached = _token_cache.get(key)
        if (
            not force_refresh
            and cached is not None
            and cached.expires_at > now + _TOKEN_REFRESH_BUFFER_SECONDS
        ):
            return cached.token

        assert self._settings.WECOM_CORP_ID is not None
        assert self._settings.WECOM_SECRET is not None
        response = self._http.get(
            f"{WECOM_API_BASE}/gettoken",
            params={
                "corpid": self._settings.WECOM_CORP_ID,
                "corpsecret": self._settings.WECOM_SECRET,
            },
        )
        response.raise_for_status()
        payload = WeComTokenResponse.model_validate(response.json())
        if payload.errcode != 0 or not payload.access_token:
            raise WeComAPIError(payload.errcode, payload.errmsg)

        expires_in = payload.expires_in or 7200
        _token_cache[key] = _CachedAccessToken(
            token=payload.access_token,
            expires_at=now + expires_in,
        )
        logger.info("wecom.token.refreshed", expires_in=expires_in)
        return payload.access_token

    def build_oauth_authorize_url(self, *, state: str) -> str:
        self._require_configured()
        redirect_uri = self._settings.WECOM_REDIRECT_URL
        if not redirect_uri:
            raise WeComNotConfiguredError("WECOM_REDIRECT_URL is not configured")

        assert self._settings.WECOM_CORP_ID is not None
        assert self._settings.WECOM_AGENT_ID is not None
        encoded_redirect = quote(redirect_uri, safe="")
        return (
            f"{WECOM_OAUTH_BASE}?appid={self._settings.WECOM_CORP_ID}"
            f"&redirect_uri={encoded_redirect}"
            "&response_type=code&scope=snsapi_base"
            f"&state={quote(state, safe='')}"
            f"&agentid={self._settings.WECOM_AGENT_ID}#wechat_redirect"
        )

    def get_user_id_by_code(self, code: str) -> str:
        access_token = self.get_access_token()
        response = self._http.get(
            f"{WECOM_API_BASE}/user/getuserinfo",
            params={"access_token": access_token, "code": code},
        )
        response.raise_for_status()
        payload = WeComUserInfoResponse.model_validate(response.json())
        if payload.errcode != 0:
            raise WeComAPIError(payload.errcode, payload.errmsg)
        if not payload.wechat_user_id:
            raise WeComAPIError(-1, "WeCom user info did not include UserId or OpenId")
        return payload.wechat_user_id

    def send_text_message(self, *, wechat_user_id: str, content: str) -> None:
        access_token = self.get_access_token()
        assert self._settings.WECOM_AGENT_ID is not None
        body: dict[str, Any] = {
            "touser": wechat_user_id,
            "msgtype": "text",
            "agentid": int(self._settings.WECOM_AGENT_ID),
            "text": {"content": content},
        }
        response = self._http.post(
            f"{WECOM_API_BASE}/message/send",
            params={"access_token": access_token},
            json=body,
        )
        response.raise_for_status()
        payload = WeComSendMessageResponse.model_validate(response.json())
        if payload.errcode != 0:
            raise WeComAPIError(payload.errcode, payload.errmsg)
        logger.info("wecom.message.sent", recipient=wechat_user_id)
