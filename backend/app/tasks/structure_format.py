"""Background worker for the Structure & Formatting tool.

The API endpoint creates the run (``queued``) and enqueues ``sf.run``. The
task seeds one ``StructureFormatCell`` per candidate cell (every non-empty cell
in the chosen columns), then processes them in batches: read each cell's
current value, apply the selected transforms in canonical order, and — when the
value actually changes — write it back and record the before/after on the cell
row (``done``); unchanged cells are ``skipped``. Progress + a Cancel are
observed between batches.

Fresh NullPool engine per task (same event-loop reason as the other task
modules). Re-querying ``pending`` makes a redelivered / resumed run idempotent.
"""
import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import BulkTableCell, StructureFormatCell, StructureFormatRun
from app.services.structure_format import apply_operations_traced
from app.tasks.celery_app import celery_app

# Cells claimed + committed per loop. Small enough that Cancel is observed
# quickly and a crash loses little; large enough to amortize commits.
BATCH = 200


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


@celery_app.task(name="sf.run")
def run_sf(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _run(db, run_id)))
    return {"run_id": run_id, "ok": True}


@celery_app.task(name="sf.resume")
def resume_sf(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _run(db, run_id)))
    return {"run_id": run_id, "ok": True}


async def _seed(db: AsyncSession, run: StructureFormatRun) -> None:
    """Materialize one pending cell per candidate (non-empty cell in scope)."""
    col_ids = [int(c) for c in (run.column_ids or [])]
    params: dict = {"run_id": run.id, "table_id": run.table_id}
    col_clause = ""
    if col_ids:
        col_clause = "AND c.column_id = ANY(:col_ids)"
        params["col_ids"] = col_ids
    await db.execute(
        text(
            f"""
            INSERT INTO structure_format_cells
                (run_id, row_id, row_position, column_id, column_name, state)
            SELECT :run_id, c.row_id, rw.position, c.column_id, col.name,
                   'pending'
            FROM bulk_table_cells c
            JOIN bulk_table_rows rw ON rw.id = c.row_id
            JOIN bulk_table_columns col ON col.id = c.column_id
            WHERE rw.table_id = :table_id
              AND c.value IS NOT NULL AND c.value <> ''
              {col_clause}
            ON CONFLICT (run_id, row_id, column_id) DO NOTHING
            """
        ),
        params,
    )
    total = (
        await db.execute(
            select(func.count())
            .select_from(StructureFormatCell)
            .where(StructureFormatCell.run_id == run.id)
        )
    ).scalar_one()
    run.total = int(total)
    run.status = "running"
    run.started_at = run.started_at or _now()
    run.last_progress_at = _now()
    await db.commit()


async def _run(db: AsyncSession, run_id: int) -> None:
    run = await db.get(StructureFormatRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    if run.status == "cancelled":
        await _finalize(db, run, cancelled=True)
        return

    if run.status == "queued":
        await _seed(db, run)

    ops = [str(o) for o in (run.operations or [])]

    while True:
        # Observe Cancel between batches.
        fresh = await db.get(StructureFormatRun, run_id)
        if fresh is None:
            return
        if fresh.status == "cancelled":
            await _finalize(db, fresh, cancelled=True)
            return

        batch = (
            (
                await db.execute(
                    select(StructureFormatCell)
                    .where(
                        StructureFormatCell.run_id == run_id,
                        StructureFormatCell.state == "pending",
                    )
                    .order_by(StructureFormatCell.id)
                    .limit(BATCH)
                )
            )
            .scalars()
            .all()
        )
        if not batch:
            break

        processed = 0
        for sfc in batch:
            cur = (
                await db.execute(
                    select(
                        BulkTableCell.value, BulkTableCell.status
                    ).where(
                        BulkTableCell.row_id == sfc.row_id,
                        BulkTableCell.column_id == sfc.column_id,
                    )
                )
            ).first()
            value = cur[0] if cur else None
            cur_status = cur[1] if cur else None
            if not value or not value.strip():
                sfc.state = "skipped"
                processed += 1
                continue
            new_value, applied = apply_operations_traced(value, ops)
            if new_value != value:
                await db.execute(
                    update(BulkTableCell)
                    .where(
                        BulkTableCell.row_id == sfc.row_id,
                        BulkTableCell.column_id == sfc.column_id,
                    )
                    .values(value=new_value, translations=None)
                )
                sfc.old_value = value
                sfc.old_status = cur_status
                sfc.new_value = new_value
                sfc.applied_ops = applied
                sfc.state = "done"
            else:
                sfc.state = "skipped"
            processed += 1

        await db.execute(
            update(StructureFormatRun)
            .where(StructureFormatRun.id == run_id)
            .values(
                done=StructureFormatRun.done + processed,
                last_progress_at=_now(),
            )
        )
        await db.commit()

    await db.refresh(run)
    await _finalize(db, run, cancelled=False)


async def _finalize(
    db: AsyncSession, run: StructureFormatRun, *, cancelled: bool
) -> None:
    if run.status in ("done", "failed"):
        return
    # Respect a Cancel that landed during the last batch — don't flip it to
    # 'done' just because processing happened to reach the end.
    if run.status == "cancelled":
        cancelled = True
    changed = (
        await db.execute(
            select(func.count())
            .select_from(StructureFormatCell)
            .where(
                StructureFormatCell.run_id == run.id,
                StructureFormatCell.state == "done",
            )
        )
    ).scalar_one()
    run.cell_count = int(changed)
    if not cancelled:
        run.status = "done"
    if run.finished_at is None:
        run.finished_at = _now()
    await db.commit()

    # Touch the table so the grid refreshes the transformed cells.
    from app.db.models import BulkTable

    await db.execute(
        update(BulkTable)
        .where(BulkTable.id == run.table_id)
        .values(updated_at=_now())
    )
    await db.commit()
