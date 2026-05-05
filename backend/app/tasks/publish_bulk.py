"""Celery wrappers for bulk publishing.

Each task creates a fresh async engine + session (NullPool), per the codebase
pattern documented in app.tasks.bulk_generation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


@celery_app.task(name="publish.seed_run")
def seed_publish_run(run_id: int) -> dict:
    asyncio.run(_seed(run_id))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="publish.publish_one_row")
def publish_one_bulk_row(run_id: int, row_id: int) -> dict:
    outcome = asyncio.run(_run_one(run_id, row_id))
    return {"run_id": run_id, "row_id": row_id, "outcome": outcome}


# ---- async cores ----

async def _seed(run_id: int) -> None:
    from app.db.models import BulkPublishRun
    from app.services.bulk_publish import candidate_row_ids

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            run = await db.get(BulkPublishRun, run_id)
            if run is None:
                return
            if run.status in ("cancelled", "done", "failed"):
                return

            candidates = await candidate_row_ids(db, run)

            # On first seed: set total. On resume: keep existing counters but
            # ensure status is 'running' going forward.
            #
            # Re-fetch the run so a Pause/Cancel issued *between* candidate
            # computation and the status flip isn't silently overwritten back
            # to 'running'. Only valid transitions out of (queued, paused) are
            # honored — other states (running/cancelled/done/failed) are left
            # alone.
            run = await db.get(BulkPublishRun, run_id)
            if run is None:
                return
            if run.status not in ("queued", "paused"):
                # Concurrent cancel / already terminal / already running — do not
                # re-enqueue or stomp state.
                return
            if run.status == "queued":
                run.total = len(candidates) + run.done + run.failed
                run.started_at = datetime.now(timezone.utc)
            run.status = "running"
            await db.commit()

            # Special case: zero candidates → mark done immediately.
            if not candidates:
                run.status = "done"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return

            for row_id in candidates:
                publish_one_bulk_row.delay(run_id, row_id)
    finally:
        await engine.dispose()


async def _run_one(run_id: int, row_id: int) -> str:
    from app.services.bulk_publish import publish_one_row

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            return await publish_one_row(db, run_id=run_id, row_id=row_id)
    finally:
        await engine.dispose()
