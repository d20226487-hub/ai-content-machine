"""Tiny in-process TTL cache for the enabled-providers list.

Why: the `/generate/providers` endpoint is hit on every page with a provider
dropdown (Single, Bulk-column config, Bulk-publish modal). The query itself
is cheap, but the round-trip adds up across N concurrent users.

Why per-process and not Redis: the table is small (a few rows) and changes
rarely. With multiple uvicorn workers each holding its own cache, a write
in one worker takes up to TTL seconds to be visible elsewhere. We accept
the staleness window in exchange for simplicity. Bump TTL down or move to
Redis-backed invalidation if real users notice.

The cache is invalidated on writes from the same process; cross-process
staleness clears on the TTL boundary.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.provider import Provider

_TTL_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class CachedProvider:
    """Read-model snapshot, decoupled from the SQLAlchemy session."""

    code: str
    display_name: str
    default_model: str | None
    available_models: tuple[str, ...]
    has_api_key: bool


_CACHE: tuple[float, tuple[CachedProvider, ...]] | None = None


def invalidate() -> None:
    """Drop the cached value. Call after any write to providers."""
    global _CACHE
    _CACHE = None


async def get_enabled_providers(db: AsyncSession) -> Sequence[CachedProvider]:
    """Return enabled providers (with key flag) from cache when fresh."""
    global _CACHE
    now = time.monotonic()
    if _CACHE is not None and now - _CACHE[0] < _TTL_SECONDS:
        return _CACHE[1]

    rows = (
        await db.execute(
            select(Provider).where(Provider.enabled.is_(True)).order_by(Provider.id)
        )
    ).scalars().all()
    snapshot = tuple(
        CachedProvider(
            code=p.code,
            display_name=p.display_name,
            default_model=p.default_model,
            available_models=tuple(p.available_models or []),
            has_api_key=bool(p.api_key_encrypted),
        )
        for p in rows
    )
    _CACHE = (now, snapshot)
    return snapshot
