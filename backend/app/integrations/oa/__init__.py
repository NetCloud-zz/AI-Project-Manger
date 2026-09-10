"""OA (RockOA / 信呼) read-only MySQL integration."""

from app.integrations.oa.client import OaAdminRecord, OaMySQLClient
from app.integrations.oa.exceptions import (
    OaNotConfiguredError,
    OaReadOnlyError,
    OaSsoError,
    OaUserNotFoundError,
)
from app.integrations.oa.sso import build_sso_sign, verify_sso_sign

__all__ = [
    "OaAdminRecord",
    "OaMySQLClient",
    "OaNotConfiguredError",
    "OaReadOnlyError",
    "OaSsoError",
    "OaUserNotFoundError",
    "build_sso_sign",
    "verify_sso_sign",
]
