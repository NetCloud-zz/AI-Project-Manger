"""Notification provider abstraction.

External messaging (WeCom, email) is optional. When credentials are absent the
application falls back to :class:`ConsoleNotificationProvider` so workers and
API handlers can always send reminders without blocking on secrets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class TaskReminderPayload:
    """Daily task update reminder."""

    task_id: int
    task_name: str
    project_name: str
    owner_id: int
    owner_name: str
    due_date: date | None
    status: str


@dataclass(frozen=True, slots=True)
class RiskNotificationPayload:
    """Risk or delay alert for a task (Phase 7+)."""

    task_id: int
    task_name: str
    project_name: str
    owner_id: int
    owner_name: str
    risk_level: str
    summary: str


class NotificationProvider(ABC):
    name: str
    #: Console output is a local simulation and must not count as real delivery.
    simulated: bool = False

    def can_reach(self, recipient_id: int) -> bool:
        """Whether this channel has an address for the user.

        Delivery records an unreachable recipient as a failure that needs a
        directory fix instead of retrying the same missing binding forever.
        """
        return True

    @abstractmethod
    def send_text_message(self, *, recipient_id: int, message: str) -> None:
        """Send a plain text message to a user."""

    @abstractmethod
    def send_task_reminder(self, payload: TaskReminderPayload) -> None:
        """Send a daily progress update reminder for one task."""

    @abstractmethod
    def send_risk_notification(self, payload: RiskNotificationPayload) -> None:
        """Send a risk / delay notification for one task."""


class NotificationProviderNotConfiguredError(RuntimeError):
    """Raised when an external provider is invoked without credentials."""
