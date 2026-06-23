"""Celery wrappers for Autotool send runs.

Fresh async engine + session per task (NullPool), per the codebase pattern in
app.tasks.publish_bulk. The seed fans out one ``send_one`` per queued item; the
watchdog recovers items orphaned by a dead worker and re-arms stalled runs.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

# An item stuck in 'sending' past this is an orphan — its worker died before the
# POST finished. Well above the 20s per-POST timeout.
_STALE_SENDING_MINUTES = 5


@celery_app.task(name="autotool.seed_run")
def seed_autotool_run(run_id: int) -> dict:
    asyncio.run(_seed(run_id))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="autotool.send_one_item")
def send_one_autotool_item(run_id: int, item_id: int) -> dict:
    outcome = asyncio.run(_send_one(run_id, item_id))
    return {"run_id": run_id, "item_id": item_id, "outcome": outcome}


@celery_app.task(name="autotool.watchdog")
def autotool_watchdog() -> dict:
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
    from app.services.autotool_run import start_run

    engine, Session = _make_session()
    try:
        async with Session() as db:
            item_ids = await start_run(db, run_id)
        for item_id in item_ids:
            send_one_autotool_item.delay(run_id, item_id)
    finally:
        await engine.dispose()


async def _send_one(run_id: int, item_id: int) -> str:
    from app.services.autotool_run import send_one_item

    engine, Session = _make_session()
    try:
        async with Session() as db:
            result = await send_one_item(db, run_id, item_id)
    finally:
        await engine.dispose()
    # The leader captured the proxy id → fan out the rest (they now carry
    # data.id) by re-running the seed.
    if result == "fanout":
        seed_autotool_run.delay(run_id)
    return result


async def _watchdog() -> None:
    from app.db.models import AutotoolRun, AutotoolRunItem
    from app.services.autotool_run import _bump

    engine, Session = _make_session()
    try:
        async with Session() as db:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(minutes=_STALE_SENDING_MINUTES)
            run_ids = (
                (
                    await db.execute(
                        select(AutotoolRun.id).where(AutotoolRun.status == "running")
                    )
                )
                .scalars()
                .all()
            )
            for rid in run_ids:
                run = await db.get(AutotoolRun, rid)
                if run is None or run.status != "running":
                    continue

                # (a) Orphaned 'sending' items → failed (+bump, which finalizes).
                stale = (
                    (
                        await db.execute(
                            select(AutotoolRunItem.id).where(
                                AutotoolRunItem.run_id == rid,
                                AutotoolRunItem.status == "sending",
                                AutotoolRunItem.updated_at < cutoff,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for iid in stale:
                    res = await db.execute(
                        update(AutotoolRunItem)
                        .where(
                            AutotoolRunItem.id == iid,
                            AutotoolRunItem.status == "sending",
                        )
                        .values(
                            status="failed",
                            detail=(
                                "Worker stopped before this page finished "
                                "(recovered by the watchdog). Retry failed to retry."
                            ),
                            updated_at=now,
                        )
                    )
                    await db.commit()
                    if (res.rowcount or 0) == 1:
                        await _bump(db, run_id=rid, field="failed")
                await db.refresh(run)
                if run.status != "running":
                    continue

                # (b) Stalled run with leftover 'queued' items (lost Celery
                # messages) → re-enqueue. Guarded by last activity so an
                # actively-draining run isn't spammed with duplicate tasks; the
                # 'queued'→'sending' claim makes a re-enqueue harmless anyway.
                last = (
                    await db.execute(
                        select(func.max(AutotoolRunItem.updated_at)).where(
                            AutotoolRunItem.run_id == rid
                        )
                    )
                ).scalar_one_or_none()
                ref = last or run.started_at
                if ref is not None and ref < cutoff:
                    has_queued = (
                        await db.execute(
                            select(AutotoolRunItem.id)
                            .where(
                                AutotoolRunItem.run_id == rid,
                                AutotoolRunItem.status == "queued",
                            )
                            .limit(1)
                        )
                    ).first()
                    if has_queued is not None:
                        # Re-seed (not enqueue-each) so leader-first ordering is
                        # respected: only the leader runs until the id is known.
                        seed_autotool_run.delay(rid)
    finally:
        await engine.dispose()
