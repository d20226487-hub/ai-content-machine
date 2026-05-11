"""Sentry initialization — shared by api and worker entrypoints.

Calling `init_sentry()` more than once is harmless; the SDK ignores
re-initializations. When `SENTRY_DSN` is empty, this function is a no-op
so dev environments don't need anything configured.
"""
from __future__ import annotations

from app.core.config import get_settings


def init_sentry(component: str) -> None:
    """component: 'api' or 'worker'. Becomes a tag on every event."""
    settings = get_settings()
    if not settings.SENTRY_DSN:
        return

    # Imported lazily so dev never pays for the SDK.
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Don't send PII by default. Override in code where you explicitly
        # want a user id attached (e.g. on auth-related events).
        send_default_pii=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            CeleryIntegration(),
        ],
    )
    sentry_sdk.set_tag("component", component)
