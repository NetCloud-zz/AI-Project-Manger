"""Shared pytest fixtures for unit tests (no live DB required for the minimal set)."""

from __future__ import annotations

import os

# Must run before app.core.config imports Settings / get_settings().
os.environ.setdefault("JWT_SECRET", "stage5-test-secret-key-32bytes-min!")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("ALLOW_INSECURE_JWT", "true")
