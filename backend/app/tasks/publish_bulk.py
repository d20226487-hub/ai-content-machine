"""Celery wrappers for bulk publishing.

Each task creates a fresh async engine + session (NullPool), per the codebase
pattern documented in app.tasks.bulk_generation.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.tasks.celery_app import celery_app


# A 'posting' job older than this is an orphan — its worker died before the
# publish finished and the counter was bumped. Must be well above the longest
# possible single publish (Custom CMS times out at 30s; WordPress with retries
# tops out around ~330s), so a slow-but-alive publish is never mistaken for dead.
_STALE_POSTING_MINUTES = 15
# A run with no new job activity for this long is considered stalled (no worker
# is making progress), so it's safe to re-enqueue leftover rows / finalize.
_STALL_MINUTES = 10


@celery_app.task(name="publish.seed_run")
def seed_publish_run(run_id: int) -> dict:
    asyncio.run(_seed(run_id))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="publish.publish_one_row")
def publish_one_bulk_row(run_id: int, row_id: int) -> dict:
    outcome = asyncio.run(_run_one(run_id, row_id))
    return {"run_id": run_id, "row_id": row_id, "outcome": outcome}


@celery_app.task(name="publish.watchdog")
def publish_watchdog() -> dict:
    """Recover bulk-publish runs stuck in 'running'. A worker that dies between
    committing a row's status='posting' and bumping the counter leaves the run
    permanently short of its total (the redelivered task skips the in-flight job
    without bumping, and Resume excludes 'posting' rows). This beat task
    reconciles those orphans, re-enqueues genuinely-lost rows, and finalizes."""
    asyncio.run(_watchdog())
    return {"ok": True}


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


async def _watchdog() -> None:
    from app.db.models import BulkPublishRun

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            run_ids = (
                (
                    await db.execute(
                        select(BulkPublishRun.id).where(
                            BulkPublishRun.status == "running"
                        )
                    )
                )
                .scalars()
                .all()
            )
            for rid in run_ids:
                try:
                    await _reconcile_run(db, rid)
                except Exception:  # noqa: BLE001 — one bad run mustn't stop the rest
                    await db.rollback()
    finally:
        await engine.dispose()


def _job_run_filter(run_id: int):
    """Shared WHERE clause: bulk-row publish jobs belonging to this run."""
    from app.db.models import PublishJob

    return (
        PublishJob.source_kind == "bulk_row",
        PublishJob.source_ref["run_id"].astext == str(run_id),
    )


async def _reconcile_run(db: AsyncSession, run_id: int) -> None:
    """Unstick one 'running' bulk-publish run. See ``publish_watchdog``."""
    from app.db.models import BulkPublishRun, PublishJob
    from app.services.bulk_publish import _bump_counter, candidate_row_ids

    run = await db.get(BulkPublishRun, run_id)
    if run is None or run.status != "running":
        return

    now = datetime.now(timezone.utc)

    # (a) Orphaned 'posting' jobs: a worker committed status='posting' then died
    # before finishing. Mark them failed so the row is accounted for, then bump
    # the counter (which finalizes the run once the total is reached). Failed
    # rows can be retried with "Re-run failed".
    orphan_ids = (
        (
            await db.execute(
                select(PublishJob.id).where(
                    *_job_run_filter(run_id),
                    PublishJob.status == "posting",
                    PublishJob.created_at
                    < now - timedelta(minutes=_STALE_POSTING_MINUTES),
                )
            )
        )
        .scalars()
        .all()
    )
    if orphan_ids:
        # Claim each orphan with a status-guarded UPDATE so a concurrent
        # watchdog tick can't double-count it: only the writer that flips
        # 'posting'→'failed' (rowcount == 1) bumps the counter.
        claimed = 0
        for jid in orphan_ids:
            res = await db.execute(
                update(PublishJob)
                .where(PublishJob.id == jid, PublishJob.status == "posting")
                .values(
                    status="failed",
                    finished_at=now,
                    error=(
                        "Worker stopped before this row finished (recovered by "
                        "the watchdog). Re-run failed rows to retry."
                    ),
                )
            )
            if (res.rowcount or 0) == 1:
                claimed += 1
        await db.commit()
        for _ in range(claimed):
            await _bump_counter(db, run_id=run_id, field="failed")
        # _bump_counter finalizes via a raw-SQL UPDATE, so the cached ORM object
        # is stale (it still reads status='running'). Refresh to see the
        # committed status before deciding whether more work remains — otherwise
        # we'd fall through and wrongly re-enqueue an already-finalized run.
        await db.refresh(run)
        if run.status != "running":
            return

    # (b) Leave actively-progressing runs alone. Any 'posting' job younger than
    # the orphan threshold may still be in flight; and a job created within the
    # stall window means a worker is making progress. Either way, don't touch it
    # — a later tick reconciles if it actually stalls.
    any_posting = (
        await db.execute(
            select(PublishJob.id).where(
                *_job_run_filter(run_id), PublishJob.status == "posting"
            ).limit(1)
        )
    ).first()
    last_created = (
        await db.execute(
            select(func.max(PublishJob.created_at)).where(*_job_run_filter(run_id))
        )
    ).scalar_one_or_none()
    if any_posting is not None:
        return
    if last_created is not None and last_created > now - timedelta(
        minutes=_STALL_MINUTES
    ):
        return

    # (c) Stalled & incomplete: re-enqueue rows that never produced a job (lost
    # Celery messages). candidate_row_ids already excludes posted/failed/posting
    # rows, so only the genuinely-unstarted leftover work is requeued.
    candidates = await candidate_row_ids(db, run)
    if candidates:
        for row_id in candidates:
            publish_one_bulk_row.delay(run_id, row_id)
        return

    # (d) No work left but still 'running' → counter drift. Recompute the
    # terminal counters from the authoritative job rows and finalize.
    rows = (
        await db.execute(
            select(PublishJob.status, func.count())
            .where(
                *_job_run_filter(run_id),
                PublishJob.status.in_(("posted", "failed", "skipped")),
            )
            .group_by(PublishJob.status)
        )
    ).all()
    by = {s: c for s, c in rows}
    await db.execute(
        text(
            "UPDATE bulk_publish_runs "
            "SET done = :d, failed = :f, skipped = :s, "
            "    status = 'done', finished_at = now() "
            "WHERE id = :id AND status = 'running'"
        ),
        {
            "d": by.get("posted", 0),
            "f": by.get("failed", 0),
            "s": by.get("skipped", 0),
            "id": run_id,
        },
    )
    await db.commit()
