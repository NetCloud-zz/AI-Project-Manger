"""WeCom integration errors."""

from __future__ import annotations


class WeComError(Exception):
    """Base error for WeCom integration."""


class WeComAPIError(WeComError):
    """WeCom API returned a non-zero errcode."""

    def __init__(self, errcode: int, errmsg: str) -> None:
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeCom API error {errcode}: {errmsg}")


class WeComNotConfiguredError(WeComError):
    """WeCom credentials or redirect URL are missing."""


class WeComOAuthStateError(WeComError):
    """OAuth state is missing, expired, or invalid."""


class WeComUserMappingError(WeComError):
    """WeCom UserID has no matching internal user."""

    def __init__(self, wechat_user_id: str) -> None:
        self.wechat_user_id = wechat_user_id
        super().__init__(f"No internal user mapped for WeCom UserID: {wechat_user_id}")
