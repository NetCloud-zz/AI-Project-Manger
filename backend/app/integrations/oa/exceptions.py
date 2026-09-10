"""OA integration exceptions."""

from __future__ import annotations


class OaError(Exception):
    """Base OA integration error."""


class OaNotConfiguredError(OaError):
    """Raised when OA MySQL / SSO settings are incomplete."""


class OaReadOnlyError(OaError):
    """Raised if any mutating SQL is attempted against OA MySQL."""


class OaUserNotFoundError(OaError):
    """Raised when an OA admin row is missing or not eligible."""

    def __init__(self, message: str, *, oa_admin_id: int | None = None) -> None:
        super().__init__(message)
        self.oa_admin_id = oa_admin_id


class OaSsoError(OaError):
    """Raised when OA SSO ticket validation fails."""
