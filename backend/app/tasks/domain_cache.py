"""Celery wrappers for bulk Custom-CMS cache clear/warm runs.

Fresh async engine + session per task (NullPool), per the codebase pattern in
app.tasks.publish_bulk / app.tasks.autotool_run. The seed fans out one
``process_one`` per queued item (parallel — each domain is independent); the
watchdog recovers items orphaned by a dead worker and re-arms a stalled run.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

# An item stuck in 'running' past this is an orphan — its worker died before the
# request finished. Comfortably above the 120s warm-cache timeout.
_STALE_RUNNING_MINUTES = 5


@celery_app.task(name="domain_cache.seed_run")
def seed_domain_cache_run(run_id: int) -> dict:
    asyncio.run(_seed(run_id))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="domain_cache.process_one_item")
def process_one_domain_cache_item(run_id: int, item_id: int) -> dict:
    outcome = asyncio.run(_process_one(run_id, item_id))
    return {"run_id": run_id, "item_id": item_id, "outcome": outcome}


@celery_app.task(name="domain_cache.watchdog")
def domain_cache_watchdog() -> dict:
    asyncio.run(_watchdog())
    return {"ok": True}


def _make_session():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    return engine, Session


async def _seed(run_id: int) -> None:
    from app.services.domain_cache import start_run

    engine, Session = _make_session()
    try:
        async with Session() as db:
            item_ids = await start_run(db, run_id)
        # Parallel fan-out: every item gets its own task. Worker concurrency
        # bounds how many run at once.
        for item_id in item_ids:
            process_one_domain_cache_item.delay(run_id, item_id)
    finally:
        await engine.dispose()


async def _process_one(run_id: int, item_id: int) -> str:
    from app.services.domain_cache import process_one_item

    engine, Session = _make_session()
    try:
        async with Session() as db:
            return await process_one_item(db, run_id, item_id)
    finally:
        await engine.dispose()


async def _watchdog() -> None:
    from app.db.models import DomainCacheRun
    from app.services.domain_cache import (
        fail_orphaned_items,
        has_in_flight_items,
        queued_item_ids,
    )

    engine, Session = _make_session()
    try:
        async with Session() as db:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=_STALE_RUNNING_MINUTES)
            run_ids = (
                (
                    await db.execute(
                        select(DomainCacheRun.id).where(
                            DomainCacheRun.status == "running"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for rid in run_ids:
                run = await db.get(DomainCacheRun, rid)
                if run is None or run.status != "running":
                    continue

                # (a) Orphaned 'running' items → failed (+bump, which finalizes).
                await fail_orphaned_items(db, rid, cutoff)
                await db.refresh(run)
                if run.status != "running":
                    continue

                # (b) Re-arm a stalled fan-out: a 'running' run with queued work
                # but nothing in flight (the enqueue was lost). The guarded
                # 'queued'->'running' claim in process_one makes a re-enqueue
                # harmless if it races a normal pickup.
                if not await has_in_flight_items(db, rid):
                    for iid in await queued_item_ids(db, rid):
                        process_one_domain_cache_item.delay(rid, iid)
    finally:
        await engine.dispose()
