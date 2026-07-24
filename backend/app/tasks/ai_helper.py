"""AI Helper mini-tool worker — distributed, rate-limited, revertable.

The API seeds the run (one ``AiHelperCell`` per selected row) and fans out one
``ai_helper.process_cell`` task per cell. Each task builds the row's variables
(applying the optional word-slice to the sliced input), renders the operator's
prompt, calls the model **through the shared provider rate limiter** (so
thousands of rows can't overwhelm the provider — same backpressure as bulk
generation, unlike link-fix's direct call), then writes the output:

  * Read mode — into the run's target column.
  * Edit mode — rewrites the target column; with a word-slice, the reply is
    spliced back onto the untouched remainder.

Each cell keeps an old/new snapshot so the whole run can be reverted. Fresh
NullPool engine per task; re-querying ``pending`` makes redelivery idempotent.
"""
import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import AiHelperCell, AiHelperRun, BulkTableCell, Provider
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import ProviderNotConfigured, get_provider
from app.services.ai_assist import first_enabled_provider_code
from app.services.ai_helper_slice import slice_first_words, splice_back
from app.services.generation_limits import (
    load_generation_limits,
    resolve_max_output_tokens,
)
from app.services.prompts import render_template
from app.services.rate_limit import get_rate_limiter
from app.services.retry import call_with_retry
from app.tasks.celery_app import celery_app

# Advisory-lock namespace for the per-run finalize ('AH').
_ADVISORY_NS = 0x4148
# Transform/extract tasks want deterministic output, not creative prose.
_TEMPERATURE = 0.2


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


@celery_app.task(name="ai_helper.process_cell")
def process_cell(run_id: int, cell_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _process_cell(db, run_id, cell_id)))
    return {"run_id": run_id, "cell_id": cell_id, "ok": True}


@celery_app.task(name="ai_helper.resume")
def resume_ai_helper(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _resume(db, run_id)))
    return {"run_id": run_id, "ok": True}


# ---------- per-cell processing ----------


async def _row_values(db: AsyncSession, row_id: int) -> dict[int, str]:
    """{column_id: value} for every cell in this row."""
    rows = (
        await db.execute(select(BulkTableCell).where(BulkTableCell.row_id == row_id))
    ).scalars().all()
    return {c.column_id: (c.value or "") for c in rows}


async def _call_ai(db: AsyncSession, run: AiHelperRun, rendered: str):
    """Run the model for one cell through the provider rate limiter.

    Returns (text, provider_code, model, prompt_tokens, completion_tokens);
    raises ProviderError / ProviderNotConfigured on failure.
    """
    code = run.provider_code or await first_enabled_provider_code(db)
    if not code:
        raise ProviderNotConfigured(
            "No AI provider is enabled. Configure one in Settings."
        )
    provider = await get_provider(db, code)
    provider_row = (
        await db.execute(select(Provider).where(Provider.code == code))
    ).scalar_one()
    model = run.model or provider_row.default_model
    gen_limits = await load_generation_limits(db)

    limiter = get_rate_limiter()
    async with limiter.acquire(
        provider_code=code,
        max_concurrency=provider_row.max_concurrency,
        requests_per_minute=provider_row.requests_per_minute,
        inter_request_delay_ms=provider_row.inter_request_delay_ms,
    ):
        result = await call_with_retry(
            provider,
            prompt=rendered,
            model=model,
            params=GenerationParams(
                temperature=_TEMPERATURE,
                max_output_tokens=resolve_max_output_tokens(
                    run.max_output_tokens, gen_limits
                ),
                thinking_budget=gen_limits.thinking_budget,
                grounding=None,
            ),
            retry_max_attempts=provider_row.retry_max_attempts,
            backoff_base_ms=provider_row.backoff_base_ms,
            backoff_jitter_ms=provider_row.backoff_jitter_ms,
            respect_retry_after=provider_row.respect_retry_after,
        )
    return (
        result.text,
        code,
        result.model,
        result.prompt_tokens,
        result.completion_tokens,
    )


async def _process_cell(db: AsyncSession, run_id: int, cell_id: int) -> None:
    cell = await db.get(AiHelperCell, cell_id)
    if cell is None or cell.state != "pending":
        return  # already processed / redelivery
    run = await db.get(AiHelperRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    if run.status == "cancelled":
        cell.state = "skipped"
        await _bump(db, run_id, "skipped")
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    target_col = cell.column_id  # the run's target column (snapshot)
    row_values = await _row_values(db, cell.row_id)
    target_current = row_values.get(target_col, "")

    slicing = (
        run.input_scope == "first_pct"
        and run.input_pct
        and run.slice_column_id is not None
    )

    # Build the prompt variables, slicing the chosen input column if configured.
    variables: dict[str, str] = {}
    for var_name, col_id in (run.variable_map or {}).items():
        cid = int(col_id)
        val = row_values.get(cid, "")
        if slicing and run.slice_column_id == cid:
            val, _tail = slice_first_words(val, int(run.input_pct))
        variables[var_name] = val
    rendered, _missing = render_template(run.prompt, variables)

    try:
        text_out, code, model, pt, ct = await _call_ai(db, run, rendered)
    except (ProviderError, ProviderNotConfigured) as e:
        await _fail_cell(db, run_id, cell, target_current, str(e))
        return
    except Exception as e:  # noqa: BLE001 — never strand the run
        await _fail_cell(db, run_id, cell, target_current, f"Unexpected error: {e}")
        return

    # Compute the value to write.
    if run.mode == "edit" and slicing and run.slice_column_id == target_col:
        _head, tail = slice_first_words(target_current, int(run.input_pct))
        new_value = splice_back(text_out, tail)
    else:
        new_value = text_out

    # Upsert the target cell (may be a brand-new column with no cell yet).
    stmt = pg_insert(BulkTableCell).values(
        row_id=cell.row_id,
        column_id=target_col,
        value=new_value,
        status="generated",
        translations=None,
    ).on_conflict_do_update(
        constraint="uq_bulk_cells_row_column",
        set_={"value": new_value, "status": "generated", "translations": None},
    )
    await db.execute(stmt)
    cell.old_value = target_current
    cell.new_value = new_value
    cell.state = "done"
    await _bump(db, run_id, "done")
    await db.commit()

    # Track-only spend as its own "AI helper" source (shows as a cost line).
    from app.services.usage import record_usage

    await record_usage(
        db,
        user_id=run.created_by_id,
        provider_code=code,
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        source="ai_helper",
        source_ref={
            "table_id": run.table_id,
            "ai_helper_run_id": run_id,
            "row_id": cell.row_id,
            "column_id": target_col,
        },
    )

    await _finalize_if_done(db, run_id)


async def _fail_cell(
    db: AsyncSession, run_id: int, cell: AiHelperCell, old_value: str, error: str
) -> None:
    cell.state = "failed"
    cell.old_value = old_value
    cell.error = error[:500]
    await _bump(db, run_id, "failed")
    await db.commit()
    await _finalize_if_done(db, run_id)


async def _bump(db: AsyncSession, run_id: int, field: str) -> None:
    """Atomic counter bump + progress stamp. ``field`` is a trusted literal."""
    if field not in ("done", "failed", "skipped"):
        raise ValueError(field)
    col = getattr(AiHelperRun, field)
    await db.execute(
        update(AiHelperRun)
        .where(AiHelperRun.id == run_id)
        .values({field: col + 1, "last_progress_at": _now()})
    )


async def _finalize_if_done(db: AsyncSession, run_id: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :rid)"),
        {"ns": _ADVISORY_NS, "rid": run_id},
    )
    run = await db.get(AiHelperRun, run_id)
    if run is None:
        await db.rollback()
        return
    # Counters are bumped via Core UPDATE, so the cached run.* are stale with
    # expire_on_commit=False. Refresh under the lock to read committed values.
    await db.refresh(run)
    if run.status != "running":
        await db.rollback()
        return
    if run.done + run.failed + run.skipped < run.total:
        await db.rollback()
        return
    run.status = "done"
    run.finished_at = _now()
    await db.commit()


async def _resume(db: AsyncSession, run_id: int) -> None:
    """Re-enqueue a run's pending cells (manual Resume / retry-failed / stall)."""
    run = await db.get(AiHelperRun, run_id)
    if run is None or run.status != "running":
        return
    run.last_progress_at = _now()
    await db.commit()

    pending = (
        (
            await db.execute(
                select(AiHelperCell.id).where(
                    AiHelperCell.run_id == run_id,
                    AiHelperCell.state == "pending",
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
        process_cell.delay(run_id, cid)
