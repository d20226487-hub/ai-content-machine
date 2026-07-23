"""Memoize grounded generations so identical prompts don't re-pay the surcharge.

A grounded Vertex call (Google Search tool) is billable per request. We key the
cache on a hash of the exact rendered prompt + model + grounding source: an
identical re-run or a duplicate-input row reuses the stored value + sources and
skips the paid call entirely. Non-grounded generations never touch this.

Entries older than ``_TTL_DAYS`` are treated as misses (the Vertex source links
expire ~30 days anyway, and callers usually want fresh research after that) and
swept by ``grounding_cache.cleanup``. Everything here is best-effort — a cache
failure must never break generation.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GroundingCache
from app.providers.base import GenerationResult

log = logging.getLogger("acm.grounding_cache")

# How long a memoized grounded result stays valid.
_TTL_DAYS = 30


def cache_key(rendered_prompt: str, model: str, grounding_source: str) -> str:
    """Stable key for a grounded generation. NUL separators so
    ``a|b`` and ``ab|`` can't collide."""
    h = hashlib.sha256()
    h.update(rendered_prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update((model or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((grounding_source or "").encode("utf-8"))
    return h.hexdigest()


async def get_cached(db: AsyncSession, key: str) -> GenerationResult | None:
    """Return a fresh (within TTL) cached result as a GenerationResult, or None.

    Token counts come back None — a hit is free, so the caller records no spend.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)
        row = (
            await db.execute(
                select(GroundingCache).where(
                    GroundingCache.cache_key == key,
                    GroundingCache.created_at >= cutoff,
                )
            )
        ).scalar_one_or_none()
    except Exception:  # noqa: BLE001 — cache read must never break generation
        log.exception("grounding cache read failed (non-fatal)")
        return None
    if row is None:
        return None
    return GenerationResult(
        text=row.value,
        model=row.model,
        finish_reason=row.finish_reason,
        grounding=row.sources,
        prompt_tokens=None,
        completion_tokens=None,
    )


async def put_cached(
    db: AsyncSession,
    key: str,
    *,
    provider_code: str,
    model: str,
    result: GenerationResult,
) -> None:
    """Upsert a freshly generated grounded result, resetting the TTL clock."""
    try:
        stmt = (
            pg_insert(GroundingCache)
            .values(
                cache_key=key,
                provider_code=provider_code,
                model=result.model or model,
                value=result.text,
                finish_reason=result.finish_reason,
                sources=result.grounding,
            )
            .on_conflict_do_update(
                index_elements=["cache_key"],
                set_={
                    "provider_code": provider_code,
                    "model": result.model or model,
                    "value": result.text,
                    "finish_reason": result.finish_reason,
                    "sources": result.grounding,
                    "created_at": func.now(),
                },
            )
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:  # noqa: BLE001 — a cache write must never break generation
        log.exception("grounding cache write failed (non-fatal)")
        await db.rollback()


async def cleanup_expired(db: AsyncSession) -> int:
    """Drop rows past the TTL. Returns how many were removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)
    res = await db.execute(
        delete(GroundingCache).where(GroundingCache.created_at < cutoff)
    )
    await db.commit()
    return int(res.rowcount or 0)
