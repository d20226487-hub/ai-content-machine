"""Celery task that runs the async bulk-generation service.

Each task processes a single (row, column) cell. Worker concurrency is
configured in docker-compose (default 4 in flight).

Important: we create a fresh async engine + session inside each task. The
global SessionLocal in app.db.session binds connections to whatever event loop
first touched it; asyncio.run() in a Celery task starts a brand new loop, and
pooled asyncpg connections from the previous loop blow up with
"Future attached to a different loop". A NullPool engine per task is the
simplest fix and the cost is one connection per task — fine for our volume.
"""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.bulk_generation import generate_one_cell
from app.tasks.celery_app import celery_app


@celery_app.task(name="bulk.generate_cell")
def generate_bulk_cell(
    table_id: int,
    row_id: int,
    column_id: int,
    *,
    override_provider_code: str | None = None,
    override_model: str | None = None,
    run_id: int | None = None,
) -> dict:
    """Generate one cell. The override pair, when both non-None, replaces
    the per-column provider/model for this run only — see the queue-wide
    override option in GenerationQueueModal.

    ``run_id`` ties this cell to a BulkGenerationRun added in migration
    0030. The service consults the run's status before doing any work
    (so a Cancel click short-circuits in-flight tasks) and atomically
    bumps the run's counters on completion. Legacy callers that omit
    run_id still work — the service skips the run bookkeeping entirely.
    """
    asyncio.run(
        _run(
            table_id,
            row_id,
            column_id,
            override_provider_code=override_provider_code,
            override_model=override_model,
            run_id=run_id,
        )
    )
    return {"table_id": table_id, "row_id": row_id, "column_id": column_id, "ok": True}


async def _run(
    table_id: int,
    row_id: int,
    column_id: int,
    *,
    override_provider_code: str | None,
    override_model: str | None,
    run_id: int | None = None,
) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    SessionPerTask: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with SessionPerTask() as db:
            await generate_one_cell(
                db,
                table_id=table_id,
                row_id=row_id,
                column_id=column_id,
                override_provider_code=override_provider_code,
                override_model=override_model,
                run_id=run_id,
            )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

# How long a run may show zero completions before we call it stalled.
#
# Deliberately generous. The naive signal — "cell has been 'generating' for a
# while" — is WRONG here: the enqueue path marks all N cells 'generating' in a
# single upsert before any work starts, so on a 1500-cell run the last cell
# legitimately sits queued for hours behind the other 1499. What actually
# indicates a stall is that NOTHING in the run has completed recently, which
# stays true regardless of queue depth. A slow provider under tight rate limits
# still lands a completion every few seconds, so 20 minutes of total silence
# means the work is genuinely gone, not slow.
_NO_PROGRESS_MINUTES = 20

_STALL_ERROR = (
    "Generation stopped before this cell ran (recovered by the watchdog). "
    "Retry with \"Only failed cells\"."
)


@celery_app.task(name="bulk_generation.watchdog")
def bulk_generation_watchdog() -> dict:
    """Recover bulk-generation runs stuck in 'running'.

    Every other long-running fan-out in the app has one of these; generation
    was the exception. Two failure shapes are handled:

      (a) Broker messages went missing (Redis restarted without persistence,
          visibility timeout expired). Cells sit at 'generating' forever, the
          counters never reach total, and the run never finalizes — no
          generate mode can pick them up either, since they're neither
          'failed' nor 'empty'.
      (b) A worker wrote the cell but died before bumping the counter, so the
          run is permanently a few short of its total with every cell settled.

    Orphans are marked 'failed' rather than re-enqueued on purpose: a
    redelivered message may still be in flight, and re-enqueueing would pay
    for the same LLM call twice. Failed cells are one click from a retry.
    """
    asyncio.run(_watchdog())
    return {"ok": True}


async def _watchdog() -> None:
    from sqlalchemy import and_, or_, select

    from app.db.models import BulkGenerationRun

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    try:
        async with Session() as db:
            # 'running' runs are the common case. 'cancelled' runs are picked up
            # only while NOT yet finalized (finished_at IS NULL): a user cancel
            # that stranded in-flight cells (OOM-killed worker / lost message)
            # whose tasks never ran to settle themselves. The cancel endpoint
            # now sweeps those synchronously, so this is a backstop — for cells
            # it missed and for runs cancelled by older code. Drained cancels
            # have finished_at set and are skipped, keeping the tick cheap.
            run_ids = (
                (
                    await db.execute(
                        select(BulkGenerationRun.id).where(
                            or_(
                                BulkGenerationRun.status == "running",
                                and_(
                                    BulkGenerationRun.status == "cancelled",
                                    BulkGenerationRun.finished_at.is_(None),
                                ),
                            )
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


async def _reconcile_run(
    db: AsyncSession,
    run_id: int,
    *,
    no_progress_minutes: float = _NO_PROGRESS_MINUTES,
) -> int:
    """Unstick one 'running'/'cancelled' generation run; return cells recovered.

    ``no_progress_minutes`` is how long the run must have been silent before we
    treat its in-flight cells as dead. The watchdog uses the generous default;
    the operator's "Recover now" button passes a short window to act on demand
    without waiting out the full stall timer — but the window is still honoured,
    so a run that produced a cell within it is left alone rather than culling
    live work. See ``bulk_generation_watchdog``.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select, text, update

    from app.db.models import BulkGenerationRun, BulkTableCell

    run = await db.get(BulkGenerationRun, run_id)
    if run is None or run.status not in ("running", "cancelled"):
        return 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=no_progress_minutes)

    # Newest activity anywhere in this run. Every settled cell stamps
    # updated_at, so this advances continuously while the queue is healthy.
    last_progress = (
        await db.execute(
            select(func.max(BulkTableCell.updated_at)).where(
                BulkTableCell.generation_run_id == run_id
            )
        )
    ).scalar_one_or_none()

    # started_at covers a run whose cells have never been touched at all.
    reference = max(
        [t for t in (last_progress, run.started_at, run.created_at) if t is not None]
    )
    if reference > cutoff:
        return 0  # progressing normally — leave it alone

    # Claim the stragglers with a status-guarded UPDATE so a worker that comes
    # back to life mid-tick can't be double-counted: only rows we actually flip
    # 'generating'->'failed' are counted into the bump.
    claimed = (
        (
            await db.execute(
                update(BulkTableCell)
                .where(
                    BulkTableCell.generation_run_id == run_id,
                    BulkTableCell.status == "generating",
                )
                .values(status="failed", error=_STALL_ERROR, finish_reason=None)
                .returning(BulkTableCell.id)
            )
        )
        .scalars()
        .all()
    )

    if claimed:
        await db.execute(
            text(
                "UPDATE bulk_generation_runs SET failed = failed + :n WHERE id = :id"
            ),
            {"n": len(claimed), "id": run_id},
        )

    # Settle the run. A 'running' run flips to 'done' once fully accounted for
    # (case (b): every cell settled but the final counter bump was lost). A
    # 'cancelled' run keeps its status but gets finished_at stamped so the
    # detail page stops showing it as ongoing. Both are guarded on the current
    # status so a live worker's own terminal write and ours converge.
    await db.execute(
        text(
            "UPDATE bulk_generation_runs "
            "SET status = 'done', finished_at = NOW() "
            "WHERE id = :id "
            "  AND status = 'running' "
            "  AND done + failed + skipped >= total"
        ),
        {"id": run_id},
    )
    await db.execute(
        text(
            "UPDATE bulk_generation_runs "
            "SET finished_at = NOW() "
            "WHERE id = :id "
            "  AND status = 'cancelled' "
            "  AND finished_at IS NULL "
            "  AND done + failed + skipped >= total"
        ),
        {"id": run_id},
    )
    await db.commit()
    return len(claimed)
