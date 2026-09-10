"""WeCom (企业微信) integration."""

from typing import Any

from app.integrations.wecom.client import WeComClient, clear_token_cache
from app.integrations.wecom.exceptions import (
    WeComAPIError,
    WeComError,
    WeComNotConfiguredError,
    WeComOAuthStateError,
    WeComUserMappingError,
)
from app.integrations.wecom.oauth_state import WeComOAuthStateStore, clear_oauth_state_memory

__all__ = [
    "WeComAPIError",
    "WeComClient",
    "WeComError",
    "WeComNotConfiguredError",
    "WeComNotificationProvider",
    "WeComOAuthStateError",
    "WeComOAuthStateStore",
    "WeComUserMappingError",
    "clear_oauth_state_memory",
    "clear_token_cache",
]


def __getattr__(name: str) -> Any:
    if name == "WeComNotificationProvider":
        from app.integrations.wecom.notification import WeComNotificationProvider

        return WeComNotificationProvider
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
