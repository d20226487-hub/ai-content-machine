"""Background worker for the multi-domain language sync.

The API endpoint creates the run (``queued``) with one ``pending``
``LanguageSyncResult`` per target, then enqueues ``langsync.run``. This task
walks the pending results in small batches: for each batch it fires the
outbound HTTP calls concurrently (bounded by a semaphore) but writes every DB
mutation back sequentially — an ``AsyncSession`` is NOT safe to touch from
several gathered coroutines at once. Counters are recomputed from the results
table after each batch so the run-detail poll shows a live progress bar.

Re-querying ``pending`` makes the task idempotent: a redelivered message, an
explicit Resume, or a retry-failed (which flips failed rows back to
``pending``) all converge by simply processing whatever is still pending.

Fresh NullPool engine per task — same event-loop reason as the other task
modules (Celery's prefork worker + a per-call ``asyncio.run``).
"""
import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import Domain, LanguageSyncResult, LanguageSyncRun
from app.services.language_sync import sync_one_domain
from app.tasks.celery_app import celery_app

# Targets claimed per loop. Each is one outbound HTTP call, so the batch
# doubles as the progress-bar granularity: 10 → ~8 updates for an 80-site run.
BATCH = 10
# Max concurrent outbound requests (matches the old synchronous fan-out cap).
CONCURRENCY = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _with_session(fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            await fn(db)
    finally:
        await engine.dispose()


@celery_app.task(name="langsync.run")
def run_langsync(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _run(db, run_id)))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="langsync.resume")
def resume_langsync(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _run(db, run_id)))
    return {"run_id": run_id, "ok": True}


async def _recompute_counts(db: AsyncSession, run_id: int) -> None:
    """Tally ok / fail / skip from the results table (authoritative) and bump
    the progress heartbeat. Pending rows count as none of the three."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE ok) AS ok,
                  count(*) FILTER (
                      WHERE state = 'done' AND NOT ok AND NOT skipped
                  ) AS fail,
                  count(*) FILTER (WHERE skipped) AS skip
                FROM language_sync_results
                WHERE run_id = :rid
                """
            ),
            {"rid": run_id},
        )
    ).first()
    await db.execute(
        update(LanguageSyncRun)
        .where(LanguageSyncRun.id == run_id)
        .values(
            ok_count=int(row.ok or 0),
            fail_count=int(row.fail or 0),
            skip_count=int(row.skip or 0),
            last_progress_at=_now(),
        )
    )
    await db.commit()


async def _run(db: AsyncSession, run_id: int) -> None:
    run = await db.get(LanguageSyncRun, run_id)
    if run is None or run.status == "done":
        return

    if run.status == "queued":
        run.status = "running"
    run.started_at = run.started_at or _now()
    run.last_progress_at = _now()
    await db.commit()

    while True:
        batch = (
            (
                await db.execute(
                    select(LanguageSyncResult)
                    .where(
                        LanguageSyncResult.run_id == run_id,
                        LanguageSyncResult.state == "pending",
                    )
                    .order_by(LanguageSyncResult.id)
                    .limit(BATCH)
                )
            )
            .scalars()
            .all()
        )
        if not batch:
            break

        # Prefetch the domains this batch targets in one query. Unknown /
        # deleted ids simply won't be in the map → handled as a skip below.
        dom_ids = [r.domain_id for r in batch if r.domain_id is not None]
        domains: dict[int, Domain] = {}
        if dom_ids:
            domains = {
                d.id: d
                for d in (
                    await db.execute(
                        select(Domain).where(
                            Domain.id.in_(dom_ids),
                            Domain.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            }

        sem = asyncio.Semaphore(CONCURRENCY)

        async def _net(r: LanguageSyncResult):
            # Network-only: must not touch `db` (shared session, concurrent).
            if r.domain_id is None:
                return None
            dom = domains.get(r.domain_id)
            if dom is None:
                return None
            async with sem:
                return await sync_one_domain(dom, list(r.languages or []))

        outcomes = await asyncio.gather(*[_net(r) for r in batch])

        # Write results back sequentially on the session.
        for r, res in zip(batch, outcomes):
            if res is None:
                r.ok = False
                r.skipped = True
                r.skip_reason = (
                    "No domain with this name (check /publish/domains)"
                    if r.domain_id is None
                    else "Domain no longer exists"
                )
                r.status_code = None
                r.detail = None
                r.elapsed_ms = None
            else:
                r.ok = res.ok
                r.skipped = res.skipped
                r.skip_reason = res.skip_reason
                r.status_code = res.status_code
                r.detail = res.detail
                r.elapsed_ms = res.elapsed_ms
            r.state = "done"
        await db.commit()

        await _recompute_counts(db, run_id)

    await _finalize(db, run_id)


async def _finalize(db: AsyncSession, run_id: int) -> None:
    run = await db.get(LanguageSyncRun, run_id)
    if run is None or run.status == "done":
        return
    await _recompute_counts(db, run_id)
    run.status = "done"
    if run.finished_at is None:
        run.finished_at = _now()
    await db.commit()
