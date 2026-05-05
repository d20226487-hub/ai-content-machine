"""Pytest config for the test suite.

Sets minimal env vars so ``app.core.config`` validates during import. Real DB
URLs aren't reached unless a specific test opts in (the in-task tests stub the
DB with fakes).
"""
from __future__ import annotations

import os

# These have to be set BEFORE any ``app.*`` import. The Settings class will
# raise otherwise. Tests that need a real DB read these and override.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost/acm_test"
)
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-do-not-use-in-prod")
# A valid Fernet key — required for app.core.crypto module import.
os.environ.setdefault(
    "FERNET_KEY", "1qfXzwXa-WYS_RYgvyZvFs0_z6AXhXTJN8VFwY0RVu0="
)
