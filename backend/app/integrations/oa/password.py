"""RockOA password verification helpers (OA stores unsalted ``md5(plain)``)."""

from __future__ import annotations

import hashlib
import hmac

# Initial passwords issued by OA; refused even when they match, so accounts
# nobody has personalised cannot be taken over with a well-known value.
OA_DEFAULT_PASSWORDS = frozenset({"123456"})


def is_oa_default_password(plain: str) -> bool:
    return plain in OA_DEFAULT_PASSWORDS


def hash_oa_password(plain: str) -> str:
    return hashlib.md5(plain.encode("utf-8")).hexdigest()  # noqa: S324 - OA format


def verify_oa_password(plain: str, stored: str | None) -> bool:
    if not plain or not stored:
        return False
    return hmac.compare_digest(hash_oa_password(plain), stored.strip().lower())
