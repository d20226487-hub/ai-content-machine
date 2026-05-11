"""Resolve effective rate-limit values for a domain.

Order of precedence (first non-None wins):
  1. domain.<column>                — per-domain override
  2. app_settings['publish_default_*']  — global default
  3. hardcoded fallback (matches the migration seed)

The actual throttling/concurrency machinery is the same Redis-backed
ProviderRateLimiter at services/rate_limit.py — we just key by
``f"domain:{domain_id}"`` to namespace from provider keys.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting, Domain
from app.services.app_settings_cache import (
    get_settings_many,
    invalidate as invalidate_setting,
)


@dataclass
class DomainRateLimits:
    requests_per_minute: int
    max_concurrency: int
    inter_request_delay_ms: int
    retry_max_attempts: int
    backoff_base_ms: int
    backoff_jitter_ms: int
    respect_retry_after: bool


_HARDCODED = DomainRateLimits(
    requests_per_minute=30,
    max_concurrency=2,
    inter_request_delay_ms=200,
    retry_max_attempts=3,
    backoff_base_ms=1000,
    backoff_jitter_ms=250,
    respect_retry_after=True,
)


_KEYS = {
    "requests_per_minute": "publish_default_requests_per_minute",
    "max_concurrency": "publish_default_max_concurrency",
    "inter_request_delay_ms": "publish_default_inter_request_delay_ms",
    "retry_max_attempts": "publish_default_retry_max_attempts",
    "backoff_base_ms": "publish_default_backoff_base_ms",
    "backoff_jitter_ms": "publish_default_backoff_jitter_ms",
    "respect_retry_after": "publish_default_respect_retry_after",
}


async def load_global_defaults(db: AsyncSession) -> DomainRateLimits:
    # Cached read — same value comes back from process-local cache for
    # subsequent calls within the TTL window. Bulk publish runs land here
    # once per row; without the cache that's K SELECTs per row.
    by_key = await get_settings_many(db, list(_KEYS.values()))

    def get_int(field: str) -> int:
        v = by_key.get(_KEYS[field])
        try:
            return int(v) if v is not None else getattr(_HARDCODED, field)
        except (TypeError, ValueError):
            return getattr(_HARDCODED, field)

    def get_bool(field: str) -> bool:
        v = by_key.get(_KEYS[field])
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return getattr(_HARDCODED, field)

    return DomainRateLimits(
        requests_per_minute=get_int("requests_per_minute"),
        max_concurrency=get_int("max_concurrency"),
        inter_request_delay_ms=get_int("inter_request_delay_ms"),
        retry_max_attempts=get_int("retry_max_attempts"),
        backoff_base_ms=get_int("backoff_base_ms"),
        backoff_jitter_ms=get_int("backoff_jitter_ms"),
        respect_retry_after=get_bool("respect_retry_after"),
    )


async def update_global_defaults(
    db: AsyncSession, values: DomainRateLimits, updated_by_id: int | None
) -> DomainRateLimits:
    for field_name, key in _KEYS.items():
        v = getattr(values, field_name)
        existing = await db.get(AppSetting, key)
        if existing is None:
            existing = AppSetting(key=key, value=v)
            db.add(existing)
        else:
            existing.value = v
        existing.updated_by_id = updated_by_id
        # Drop the cached value so this worker sees the new one immediately.
        # Cross-worker propagation happens on the cache TTL boundary.
        invalidate_setting(key)
    await db.commit()
    return values


async def resolve_for_domain(
    db: AsyncSession, domain: Domain
) -> DomainRateLimits:
    """Effective rate-limit values for one domain (override → global → fallback)."""
    g = await load_global_defaults(db)

    def pick(override: object, default: object) -> object:
        return default if override is None else override

    return DomainRateLimits(
        requests_per_minute=int(pick(domain.requests_per_minute, g.requests_per_minute)),
        max_concurrency=int(pick(domain.max_concurrency, g.max_concurrency)),
        inter_request_delay_ms=int(pick(domain.inter_request_delay_ms, g.inter_request_delay_ms)),
        retry_max_attempts=int(pick(domain.retry_max_attempts, g.retry_max_attempts)),
        backoff_base_ms=int(pick(domain.backoff_base_ms, g.backoff_base_ms)),
        backoff_jitter_ms=int(pick(domain.backoff_jitter_ms, g.backoff_jitter_ms)),
        respect_retry_after=bool(pick(domain.respect_retry_after, g.respect_retry_after)),
    )


def domain_rate_key(domain_id: int) -> str:
    """Namespace used with services.rate_limit.ProviderRateLimiter.acquire()."""
    return f"domain:{domain_id}"
