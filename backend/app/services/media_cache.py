"""Per-domain media-upload cache.

The WP client calls ``cache.lookup(url)`` before downloading. On a hit, the
cached ``wp_media_id`` is reused. On a miss, the client uploads as usual,
then calls ``cache.remember(...)``.

Concurrency: when many rows of a bulk run reference the same image URL,
multiple workers may race past ``lookup`` together and each upload. The
duplicate-write is handled at insert time with ``ON CONFLICT DO NOTHING``;
the second writer's upload becomes a wasted media item on WP, which is
acceptable in v1 (uncommon, harmless).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MediaUpload


class MediaCache:
    def __init__(self, db: AsyncSession, domain_id: int) -> None:
        self._db = db
        self._domain_id = domain_id

    async def lookup(self, source_url: str) -> int | None:
        """Return the cached wp_media_id for this URL, or None."""
        row = await self._db.get(MediaUpload, (self._domain_id, source_url))
        if row is None:
            return None
        return row.wp_media_id

    async def remember(
        self,
        source_url: str,
        wp_media_id: int,
        *,
        content_type: str | None = None,
        size_bytes: int | None = None,
    ) -> None:
        stmt = (
            pg_insert(MediaUpload)
            .values(
                domain_id=self._domain_id,
                source_url=source_url,
                wp_media_id=wp_media_id,
                content_type=content_type,
                size_bytes=size_bytes,
            )
            .on_conflict_do_nothing(index_elements=["domain_id", "source_url"])
        )
        await self._db.execute(stmt)
        await self._db.commit()


async def clear_for_domain(db: AsyncSession, domain_id: int) -> int:
    """Drop every cached entry for one domain. Returns rows deleted."""
    from sqlalchemy import delete as sa_delete

    result = await db.execute(
        sa_delete(MediaUpload).where(MediaUpload.domain_id == domain_id)
    )
    await db.commit()
    return result.rowcount or 0


async def count_for_domain(db: AsyncSession, domain_id: int) -> int:
    from sqlalchemy import func

    result = await db.execute(
        select(func.count())
        .select_from(MediaUpload)
        .where(MediaUpload.domain_id == domain_id)
    )
    return int(result.scalar_one() or 0)
