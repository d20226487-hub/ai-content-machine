"""Tiny in-process TTL cache for `app_settings` rows.

Why: services like publish_rate_limit.py read several `app_settings` rows on
every row publish (`publish_default_*` for global rate-limit defaults). Each
read is a full Postgres round-trip. With N concurrent workers publishing M
rows, that's N×M×K reads of a half-dozen rows that change rarely.

Why per-process and not Redis: same reasoning as `provider_cache.py` — the
settings change rarely, the staleness window is bounded by TTL, and Redis
adds a moving part for marginal gain at this scale. Each uvicorn worker /
celery worker holds its own copy; cross-process invalidation is "wait up to
TTL seconds" and we accept that.

Single shared TTL (default 30 s) for everything in the cache. Calls go
through `get_setting(db, key)` which transparently consults the cache and
falls back to the DB on miss/expiry. Writers must call `invalidate(key)`
(or `invalidate_all()`) so the in-process cache reflects the new value
immediately for the worker that did the write.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting

_TTL_SECONDS = 30.0

# Each entry: key → (expiry_monotonic, value_or_sentinel).
# Sentinel `_MISSING` distinguishes "we know the row doesn't exist" from
# "we don't know yet" — without that, every miss would re-query.
_MISSING = object()
_CACHE: dict[str, tuple[float, Any]] = {}


def invalidate(key: str) -> None:
    _CACHE.pop(key, None)


def invalidate_all() -> None:
    _CACHE.clear()


async def get_setting(db: AsyncSession, key: str) -> Any:
    """Return the cached value for `key`, or fetch + cache. None if no row."""
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and cached[0] > now:
        return None if cached[1] is _MISSING else cached[1]

    row = await db.get(AppSetting, key)
    value: Any = row.value if row is not None else _MISSING
    _CACHE[key] = (now + _TTL_SECONDS, value)
    return None if value is _MISSING else value


async def get_settings_many(
    db: AsyncSession, keys: list[str]
) -> dict[str, Any]:
    """Fetch many keys, using cache where possible. Missing rows are absent
    from the result dict (callers fall back to defaults themselves).

    Cheaper than calling get_setting in a loop when several keys are missing
    from the cache at once: one SELECT covers all the misses.
    """
    now = time.monotonic()
    out: dict[str, Any] = {}
    misses: list[str] = []
    for k in keys:
        c = _CACHE.get(k)
        if c is not None and c[0] > now:
            if c[1] is not _MISSING:
                out[k] = c[1]
        else:
            misses.append(k)

    if misses:
        rows = (
            await db.execute(select(AppSetting).where(AppSetting.key.in_(misses)))
        ).scalars().all()
        seen: set[str] = set()
        for r in rows:
            seen.add(r.key)
            _CACHE[r.key] = (now + _TTL_SECONDS, r.value)
            out[r.key] = r.value
        # Anything still missing → cache the negative result.
        for k in misses:
            if k not in seen:
                _CACHE[k] = (now + _TTL_SECONDS, _MISSING)
    return out
