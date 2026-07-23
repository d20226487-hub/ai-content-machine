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
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, text, update
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
from app.services.link_fix_apply import expected_links_for_row, reverify_in_place
from app.tasks.celery_app import celery_app


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


@celery_app.task(name="linkfix.replace_cell")
def replace_cell(run_id: int, cell_id: int) -> dict:
    """Deterministic per-cell sibling of ``fix_cell`` for ``method='replace'``
    runs: swap each seeded wrong link for its (re-derived) expected link in
    place. Same fan-out / progress / finalize machinery — no LLM call."""
    asyncio.run(_with_session(lambda db: _replace_cell(db, run_id, cell_id)))
    return {"run_id": run_id, "cell_id": cell_id, "ok": True}


@celery_app.task(name="linkfix.strip_cell")
def strip_cell(run_id: int, cell_id: int) -> dict:
    """Deterministic per-cell sibling of ``fix_cell`` for ``method='strip'``
    runs: remove each seeded crawl/HTTP-status link's ``<a>`` wrapper in place,
    keeping the anchor text. Same fan-out / progress / finalize machinery — no
    LLM call, and no expected-link derivation (a broken link has no
    replacement)."""
    asyncio.run(_with_session(lambda db: _strip_cell(db, run_id, cell_id)))
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
    expected = await expected_links_for_row(db, run=run, row_id=cell.row_id)

    try:
        new_text, code, model, pt, ct = await fix_links_text(
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
        prompt_tokens=pt,
        completion_tokens=ct,
        source="brain_fix_links",
        source_ref={
            # table_id lets the table cost panel attribute this spend; the fix
            # writes into run.table_id's columns.
            "table_id": run.table_id,
            "link_fix_run_id": run_id,
            "row_id": cell.row_id,
            "column_id": cell.column_id,
        },
    )

    await _finalize_if_done(db, run_id)


async def _replace_cell(db: AsyncSession, run_id: int, cell_id: int) -> None:
    """Deterministic in-place link swap for one seeded cell. The links to swap
    were stored on the cell's ``violations`` at seed time; the EXPECTED link is
    re-derived here (never trusted from the client). Mirrors ``_fix_cell``'s
    idempotency, cancel handling, progress bump and finalize."""
    from app.services.translation_links import (
        compute_row_breakdown,
        parse_domains,
        replace_link_in_text,
        strip_link_in_text,
    )

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

    want_links = [
        str(v["link"])
        for v in (cell.violations or [])
        if isinstance(v, dict) and v.get("link")
    ]
    source = (
        await db.get(LinkCheckRun, run.source_run_id)
        if run.source_run_id
        else None
    )
    cfg = source.translation_config if source else None
    if not cfg or not want_links:
        cell.state = "skipped"
        await _bump(db, run_id, "skipped")
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    try:
        orig_col = int(cfg["original_column_id"])
        trans_col = int(cfg["translated_column_id"])
        lang_col = int(cfg["lang_column_id"])
        domain_cols = [int(c) for c in cfg.get("internal_domain_column_ids", [])]
        product_domains = cfg.get("product_domains", []) or []
        exceptions = cfg.get("exceptions", []) or []
        default_langs = cfg.get("product_default_langs", {}) or {}
        internal_t = cfg.get("internal_treatment", "skip")
        external_t = cfg.get("external_treatment", "skip")

        vals = {
            cid: val
            for cid, val in (
                await db.execute(
                    select(BulkTableCell.column_id, BulkTableCell.value).where(
                        BulkTableCell.row_id == cell.row_id,
                        BulkTableCell.column_id.in_(
                            [orig_col, trans_col, lang_col, *domain_cols]
                        ),
                    )
                )
            ).all()
        }
        internal_domains: list[str] = []
        for dc in domain_cols:
            internal_domains += parse_domains(vals.get(dc))
        bd = compute_row_breakdown(
            vals.get(orig_col),
            vals.get(trans_col),
            (vals.get(lang_col) or "").strip(),
            internal_domains=internal_domains,
            product_domains=product_domains,
            exceptions=exceptions,
            internal_treatment=internal_t,
            external_treatment=external_t,
            default_langs=default_langs,
        )
        tag_by_url = {t["url"]: t for t in bd["translation"] if t["kind"] != "ok"}

        old_value = vals.get(trans_col)
        new_value = old_value or ""
        applied: list[dict] = []
        for link in want_links:
            tag = tag_by_url.get(link)
            if tag is None or not new_value:
                continue  # no longer a problem link / empty cell
            expected = tag.get("expected")
            if expected:
                new_value, n = replace_link_in_text(new_value, link, expected)
            else:
                new_value, n = strip_link_in_text(new_value, link)
            if n > 0:
                applied.append(
                    {
                        "problem": "hallucinated",
                        "link": link,
                        "detail_code": "not_in_expected",
                        "status_code": None,
                    }
                )

        changed = new_value != (old_value or "")
        cell.source_value = old_value
        cell.old_value = old_value
        cell.violations = applied
        if changed:
            # Preserve the cell's status (a targeted fix isn't a regeneration),
            # but drop any cached translation — it no longer matches the source.
            await db.execute(
                update(BulkTableCell)
                .where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == trans_col,
                )
                .values(value=new_value, translations=None)
            )
            cell.new_value = new_value
            cell.state = "done"
            await _bump(db, run_id, "done")
        else:
            cell.new_value = None
            cell.state = "skipped"
            await _bump(db, run_id, "skipped")
        await db.commit()
    except Exception as e:  # noqa: BLE001 — never strand the run on bad data
        await db.rollback()
        cell = await db.get(LinkFixCell, cell_id)
        if cell is not None and cell.state == "pending":
            cell.state = "failed"
            cell.error = str(e)[:500]
            await _bump(db, run_id, "failed")
            await db.commit()
    await _finalize_if_done(db, run_id)


async def _strip_cell(db: AsyncSession, run_id: int, cell_id: int) -> None:
    """Deterministic in-place ``<a>``-unwrap for one seeded crawl cell. The links
    to strip were stored on the cell's ``violations`` at seed time. Unlike
    ``_replace_cell`` there's no config / expected-link derivation — a broken
    link is simply removed, anchor text kept. Mirrors the idempotency, cancel
    handling, progress bump and finalize of its siblings; on success it stamps
    the source check run's matching crawl violations ``solved`` so the run page
    strikes them through (and Revert can clear that)."""
    from app.services.translation_links import strip_link_in_text

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

    want_links = [
        str(v["link"])
        for v in (cell.violations or [])
        if isinstance(v, dict) and v.get("link")
    ]
    try:
        old_value = (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == cell.column_id,
                )
            )
        ).scalar_one_or_none()

        new_value = old_value or ""
        applied: list[dict] = []
        for link in want_links:
            if not new_value:
                break
            new_value, n = strip_link_in_text(new_value, link)
            if n > 0:
                applied.append(
                    {
                        "problem": "broken",
                        "link": link,
                        "detail_code": None,
                        "status_code": None,
                    }
                )

        changed = new_value != (old_value or "")
        cell.source_value = old_value
        cell.old_value = old_value
        cell.violations = applied
        if changed:
            # Preserve the cell's status (a targeted strip isn't a regeneration),
            # but drop any cached translation — it no longer matches the source.
            await db.execute(
                update(BulkTableCell)
                .where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == cell.column_id,
                )
                .values(value=new_value, translations=None)
            )
            cell.new_value = new_value
            cell.state = "done"
            await _bump(db, run_id, "done")
            # Stamp the originating crawl violations 'solved' for the links we
            # actually removed (struck through on the run page; Revert clears).
            if run.source_run_id is not None and applied:
                await db.execute(
                    update(LinkCheckViolation)
                    .where(
                        LinkCheckViolation.run_id == run.source_run_id,
                        LinkCheckViolation.row_id == cell.row_id,
                        LinkCheckViolation.column_id == cell.column_id,
                        LinkCheckViolation.link.in_([a["link"] for a in applied]),
                    )
                    .values(resolution="solved")
                )
        else:
            cell.new_value = None
            cell.state = "skipped"
            await _bump(db, run_id, "skipped")
        await db.commit()
    except Exception as e:  # noqa: BLE001 — never strand the run on bad data
        await db.rollback()
        cell = await db.get(LinkFixCell, cell_id)
        if cell is not None and cell.state == "pending":
            cell.state = "failed"
            cell.error = str(e)[:500]
            await _bump(db, run_id, "failed")
            await db.commit()
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
    if run is None:
        await db.rollback()
        return
    # The per-cell bump uses a Core UPDATE, so with expire_on_commit=False the
    # cached run.* counters + status are STALE — trusting them here meant a run
    # whose cells all finished could stay 'running' forever. Refresh under the
    # advisory lock to read the committed status + counters.
    await db.refresh(run)
    if run.status != "running":
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
    # (the AI corrector runs in juxtapose mode), never crawl. Strip runs target
    # crawl violations and already stamped them per-link in the worker — a
    # juxtapose re-verify here would mislabel a combined run's omitted/
    # hallucinated violations, so skip it for them.
    if run.method != "strip":
        await reverify_in_place(db, run)

    await db.commit()


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
    task = {"replace": replace_cell, "strip": strip_cell}.get(run.method, fix_cell)
    for cid in pending:
        task.delay(run_id, cid)
