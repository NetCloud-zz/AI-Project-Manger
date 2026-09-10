"""Notification provider registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.notifications.console import ConsoleNotificationProvider
from app.notifications.provider import NotificationProvider

if TYPE_CHECKING:
    from app.integrations.wecom.notification import WeComNotificationProvider

_console_provider = ConsoleNotificationProvider()
_wecom_provider: WeComNotificationProvider | None = None


def get_notification_provider() -> NotificationProvider:
    """Return the active notification provider."""
    global _wecom_provider
    if get_settings().wecom_configured:
        if _wecom_provider is None:
            from app.integrations.wecom.notification import WeComNotificationProvider

            _wecom_provider = WeComNotificationProvider()
        return _wecom_provider
    return _console_provider


def reset_notification_providers_for_tests() -> None:
    """Clear cached providers (for tests only)."""
    global _wecom_provider
    _wecom_provider = None
