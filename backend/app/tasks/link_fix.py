"""AI link-fix pass for the Link Checker (distributed + revertable).

The API endpoint seeds the run synchronously (materializes one
``LinkFixCell`` per flagged output cell with a pre-fix snapshot) and fans
out one ``linkfix.fix_cell`` task per cell. Each task re-reads the cell's
current value, gathers the row's EXPECTED links, runs the Brain
``fix_links`` prompt (integrate missing / fix typo / remove hallucinated),
and writes the corrected value back — keeping the before/after snapshot so
the whole run can be reverted.

When the last cell finishes, finalize (advisory-locked, runs once) flips the
run ``done`` and re-juxtaposes the corrected cells IN PLACE — stamping the
originating check run's violations 'solved' / 'unsolved' (no separate
re-check job) so the user sees the outcome on the same check-run page.

Fresh NullPool engine per task — same event-loop reason as the other task
modules. Re-querying ``pending`` makes a redelivered / resumed task
idempotent.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import (
    BulkTableCell,
    LinkCheckRun,
    LinkCheckViolation,
    LinkFixCell,
    LinkFixRun,
)
from app.providers.base import ProviderError
from app.providers.registry import ProviderNotConfigured
from app.services.brain import fix_links_text
from app.services.link_check import (
    extract_expected_links,
    extract_output_links,
    juxtapose,
    normalize_link,
)
from app.services.translation_links import compute_expected_links, parse_domains
from app.tasks.celery_app import celery_app


async def _expected_links_for_row(
    db: AsyncSession, *, run: LinkFixRun, row_id: int
) -> list[str]:
    """Expected links for one row.

    Translation runs have no materialized expected column — recompute the
    localized expected links from the source run's ``translation_config`` (read
    the row's original/lang/domain cells). Normal runs read the snapshotted
    expected columns. ``db.get`` on the source run is identity-mapped, so this
    stays one extra query per session."""
    cfg = None
    if run.source_run_id:
        source = await db.get(LinkCheckRun, run.source_run_id)
        cfg = source.translation_config if source else None

    if cfg:
        orig_col = int(cfg["original_column_id"])
        lang_col = int(cfg["lang_column_id"])
        domain_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
        rows = (
            await db.execute(
                select(BulkTableCell.column_id, BulkTableCell.value).where(
                    BulkTableCell.row_id == row_id,
                    BulkTableCell.column_id.in_([orig_col, lang_col, *domain_cols]),
                )
            )
        ).all()
        vals = {cid: val for cid, val in rows}
        lang = (vals.get(lang_col) or "").strip()
        if not lang:
            return []
        internal_domains: list[str] = []
        for dc in domain_cols:
            internal_domains += parse_domains(vals.get(dc))
        return compute_expected_links(
            vals.get(orig_col),
            lang,
            internal_domains=internal_domains,
            product_domains=cfg.get("product_domains", []),
            exceptions=cfg.get("exceptions", []),
            internal_treatment=cfg.get("internal_treatment", "skip"),
            external_treatment=cfg.get("external_treatment", "skip"),
            default_langs=cfg.get("product_default_langs", {}) or {},
        )

    exp_cols = [int(c) for c in (run.expected_column_ids or [])]
    if not exp_cols:
        return []
    cells = (
        await db.execute(
            select(BulkTableCell.value).where(
                BulkTableCell.row_id == row_id,
                BulkTableCell.column_id.in_(exp_cols),
            )
        )
    ).scalars().all()
    out: list[str] = []
    for v in cells:
        out += extract_expected_links(v)
    return out

# Advisory-lock namespace for the per-run finalize ('LF').
_ADVISORY_NS = 0x4C46


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


# ---------- Celery entrypoints ----------


@celery_app.task(name="linkfix.fix_cell")
def fix_cell(run_id: int, cell_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _fix_cell(db, run_id, cell_id)))
    return {"run_id": run_id, "cell_id": cell_id, "ok": True}


@celery_app.task(name="linkfix.resume")
def resume_link_fix(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _resume(db, run_id)))
    return {"run_id": run_id, "ok": True}


# ---------- per-cell fix ----------


async def _fix_cell(db: AsyncSession, run_id: int, cell_id: int) -> None:
    cell = await db.get(LinkFixCell, cell_id)
    if cell is None or cell.state != "pending":
        return  # already processed / redelivery

    run = await db.get(LinkFixRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    if run.status == "cancelled":
        cell.state = "skipped"
        await _bump(db, run_id, "skipped")
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    # Corrected content is written to the run's target column (or back to the
    # source column when overwriting). We read the SOURCE content to fix, and
    # snapshot the TARGET cell's current value for revert.
    target_col = run.target_column_id or cell.column_id

    # Re-read the SOURCE cell's current value — the AI fixes what's really
    # there now; also kept as source_value for the before/after display.
    content = (
        await db.execute(
            select(BulkTableCell.value).where(
                BulkTableCell.row_id == cell.row_id,
                BulkTableCell.column_id == cell.column_id,
            )
        )
    ).scalar_one_or_none()
    target_current = (
        await db.execute(
            select(BulkTableCell.value).where(
                BulkTableCell.row_id == cell.row_id,
                BulkTableCell.column_id == target_col,
            )
        )
    ).scalar_one_or_none()

    if not content or not content.strip():
        # Nothing to fix (e.g. an omitted link whose target cell is empty).
        cell.state = "skipped"
        cell.source_value = content
        cell.old_value = target_current
        await _bump(db, run_id, "skipped")
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    # Expected links for this row — recomputed for translation runs (no
    # materialized column), else read from the snapshotted expected columns.
    expected = await _expected_links_for_row(db, run=run, row_id=cell.row_id)

    try:
        new_text, code, model = await fix_links_text(
            db,
            content=content,
            expected_links=expected,
            violations=list(cell.violations or []),
            system_override=run.prompt,
        )
    except (ProviderError, ProviderNotConfigured) as e:
        cell.state = "failed"
        cell.source_value = content
        cell.old_value = target_current
        cell.error = str(e)
        await _bump(db, run_id, "failed")
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    # Write the corrected value into the target cell (upsert — the target
    # column may be brand-new with no cell yet). Clear cached translations.
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(BulkTableCell).values(
        row_id=cell.row_id,
        column_id=target_col,
        value=new_text,
        status="generated",
        translations=None,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_bulk_cells_row_column",
        set_={"value": new_text, "status": "generated", "translations": None},
    )
    await db.execute(stmt)
    cell.source_value = content
    cell.old_value = target_current
    cell.new_value = new_text
    cell.state = "done"
    await _bump(db, run_id, "done")
    await db.commit()

    # Track-only spend.
    from app.services.usage import record_usage

    await record_usage(
        db,
        user_id=run.created_by_id,
        provider_code=code,
        model=model,
        prompt_tokens=None,
        completion_tokens=None,
        source="brain_fix_links",
        source_ref={
            "link_fix_run_id": run_id,
            "row_id": cell.row_id,
            "column_id": cell.column_id,
        },
    )

    await _finalize_if_done(db, run_id)


async def _bump(db: AsyncSession, run_id: int, field: str) -> None:
    """Atomic counter bump + progress stamp. ``field`` is a trusted literal."""
    if field not in ("done", "failed", "skipped"):
        raise ValueError(field)
    col = getattr(LinkFixRun, field)
    await db.execute(
        update(LinkFixRun)
        .where(LinkFixRun.id == run_id)
        .values({field: col + 1, "last_progress_at": _now()})
    )


# ---------- finalize + auto re-check ----------


async def _finalize_if_done(db: AsyncSession, run_id: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :rid)"),
        {"ns": _ADVISORY_NS, "rid": run_id},
    )
    run = await db.get(LinkFixRun, run_id)
    if run is None or run.status != "running":
        await db.rollback()
        return
    if run.done + run.failed + run.skipped < run.total:
        await db.rollback()
        return

    run.status = "done"
    run.finished_at = _now()

    # Re-verify IN PLACE (no new job): re-juxtapose each corrected cell and
    # stamp the SOURCE check run's matching violations 'solved' / 'unsolved'
    # so the original run page shows what the fix did. We re-juxtapose only
    # (the AI corrector runs in juxtapose mode), never crawl.
    await _reverify_in_place(db, run)

    await db.commit()


async def _reverify_in_place(db: AsyncSession, run: LinkFixRun) -> None:
    """Re-juxtapose the cells this run corrected and stamp the originating
    check run's violations. NULL stays = untouched; 'solved' = the flagged
    link is gone from the corrected cell, 'unsolved' = still present."""
    if run.source_run_id is None:
        return

    cells = (
        (
            await db.execute(
                select(LinkFixCell).where(
                    LinkFixCell.run_id == run.id,
                    LinkFixCell.state == "done",
                )
            )
        )
        .scalars()
        .all()
    )
    for cell in cells:
        target_col = run.target_column_id or cell.column_id
        corrected = (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == target_col,
                )
            )
        ).scalar_one_or_none()

        expected = await _expected_links_for_row(db, run=run, row_id=cell.row_id)

        omitted, hallucinated = juxtapose(
            extract_output_links(corrected), expected
        )
        still = {normalize_link(u) for u in omitted + hallucinated}

        violations = (
            (
                await db.execute(
                    select(LinkCheckViolation).where(
                        LinkCheckViolation.run_id == run.source_run_id,
                        LinkCheckViolation.row_id == cell.row_id,
                        LinkCheckViolation.column_id == cell.column_id,
                        LinkCheckViolation.problem.in_(("omitted", "hallucinated")),
                    )
                )
            )
            .scalars()
            .all()
        )
        for v in violations:
            v.resolution = (
                "unsolved" if normalize_link(v.link) in still else "solved"
            )


# ---------- resume ----------


async def _resume(db: AsyncSession, run_id: int) -> None:
    """Re-enqueue a run's pending cells (manual Resume / stall recovery)."""
    run = await db.get(LinkFixRun, run_id)
    if run is None or run.status != "running":
        return
    run.last_progress_at = _now()
    await db.commit()

    pending = (
        (
            await db.execute(
                select(LinkFixCell.id).where(
                    LinkFixCell.run_id == run_id,
                    LinkFixCell.state == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    if not pending:
        await _finalize_if_done(db, run_id)
        return
    for cid in pending:
        fix_cell.delay(run_id, cid)
