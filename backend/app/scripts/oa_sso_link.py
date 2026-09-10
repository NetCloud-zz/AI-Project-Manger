"""Generate a one-time OA → project-agent SSO jump URL.

Usage::

    python -m app.scripts.oa_sso_link --uid 88

Requires OA_SSO_SECRET and a public API base (BACKEND_PUBLIC_URL or default).
"""

from __future__ import annotations

import argparse
import time
from urllib.parse import urlencode

from app.core.config import get_settings
from app.integrations.oa.sso import build_sso_sign


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OA SSO jump URL")
    parser.add_argument("--uid", type=int, required=True, help="OA osri_admin.id")
    parser.add_argument(
        "--base",
        default=None,
        help="API public base, e.g. http://10.x.x.x:8000 (default: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.OA_SSO_SECRET:
        raise SystemExit("OA_SSO_SECRET is not set")

    ts = int(time.time())
    sign = build_sso_sign(uid=args.uid, ts=ts, secret=settings.OA_SSO_SECRET)
    base = (args.base or "http://127.0.0.1:8000").rstrip("/")
    query = urlencode({"uid": args.uid, "ts": ts, "sign": sign})
    print(f"{base}/api/v1/auth/oa/sso?{query}")


if __name__ == "__main__":
    main()
