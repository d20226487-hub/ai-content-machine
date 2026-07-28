"""AI Helper mini-tool worker — distributed, rate-limited, revertable.

The API seeds the run (one ``AiHelperCell`` per (selected row, output column))
and fans out work by engine:

  * **structured** — one ``ai_helper.process_row`` task per row: build the row's
    variables (with the optional word-slice), render the shared base prompt +
    an appended "return ONLY a JSON object with keys …" instruction, make ONE
    model call, then route the parsed JSON to each output column (missing key ⇒
    that cell ``skipped``). Cheapest: 1 call/row.
  * **per_output** — one ``ai_helper.process_cell`` task per cell: render that
    output's own prompt, make ONE model call, write just that column. N calls/row
    but focused prompts. This reuses v1's single-output path per output.

Both write through the shared provider rate limiter (so thousands of rows can't
overwhelm the provider — same backpressure as bulk generation), honour per-output
write/edit (edit on the sliced column splices the reply back onto the untouched
remainder), and snapshot each cell's old/new value so the whole run reverts.

Fresh NullPool engine per task; re-querying ``pending`` makes redelivery
idempotent. Its spend lands on the ``ai_helper`` usage source (one cost line).
"""
import asyncio
import json
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
from app.services.ai_helper_json import extract_json_object
from app.services.ai_helper_outputs import (
    build_structured_suffix,
    effective_engine,
    effective_outputs,
)
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
    """per_output engine: one AI call for one output cell."""
    asyncio.run(_with_session(lambda db: _process_cell(db, run_id, cell_id)))
    return {"run_id": run_id, "cell_id": cell_id, "ok": True}


@celery_app.task(name="ai_helper.process_row")
def process_row(run_id: int, row_id: int) -> dict:
    """structured engine: one AI call for a whole row, routed to its outputs."""
    asyncio.run(_with_session(lambda db: _process_row(db, run_id, row_id)))
    return {"run_id": run_id, "row_id": row_id, "ok": True}


@celery_app.task(name="ai_helper.resume")
def resume_ai_helper(run_id: int) -> dict:
    asyncio.run(_with_session(lambda db: _resume(db, run_id)))
    return {"run_id": run_id, "ok": True}


# ---------- shared helpers ----------


async def _row_values(db: AsyncSession, row_id: int) -> dict[int, str]:
    """{column_id: value} for every cell in this row."""
    rows = (
        await db.execute(select(BulkTableCell).where(BulkTableCell.row_id == row_id))
    ).scalars().all()
    return {c.column_id: (c.value or "") for c in rows}


def _is_slicing(run: AiHelperRun) -> bool:
    return bool(
        run.input_scope == "first_pct"
        and run.input_pct
        and run.slice_column_id is not None
    )


def _variables_for(run: AiHelperRun, row_values: dict[int, str]) -> dict[str, str]:
    """Prompt variables for a row, applying the word-slice to the sliced input."""
    slicing = _is_slicing(run)
    variables: dict[str, str] = {}
    for var_name, col_id in (run.variable_map or {}).items():
        cid = int(col_id)
        val = row_values.get(cid, "")
        if slicing and run.slice_column_id == cid:
            val, _tail = slice_first_words(val, int(run.input_pct))
        variables[var_name] = val
    return variables


def _value_to_write(
    run: AiHelperRun, output: dict, text_out: str, row_values: dict[int, str]
) -> str:
    """The value to store for an output. Edit on the sliced column splices the
    reply back onto the untouched remainder; everything else writes as-is."""
    col = output["column_id"]
    if output["mode"] == "edit" and _is_slicing(run) and run.slice_column_id == col:
        _head, tail = slice_first_words(row_values.get(col, ""), int(run.input_pct))
        return splice_back(text_out, tail)
    return text_out


async def _upsert_cell_value(
    db: AsyncSession, row_id: int, column_id: int, new_value: str
) -> None:
    """Write a bulk-table cell (may be a brand-new column with no cell yet)."""
    stmt = pg_insert(BulkTableCell).values(
        row_id=row_id,
        column_id=column_id,
        value=new_value,
        status="generated",
        translations=None,
    ).on_conflict_do_update(
        constraint="uq_bulk_cells_row_column",
        set_={"value": new_value, "status": "generated", "translations": None},
    )
    await db.execute(stmt)


async def _call_ai(db: AsyncSession, run: AiHelperRun, rendered: str):
    """Run the model for one call through the provider rate limiter.

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


async def _record_usage(
    db: AsyncSession,
    run: AiHelperRun,
    code: str,
    model: str,
    pt: int | None,
    ct: int | None,
    row_id: int,
    *,
    column_id: int | None = None,
    column_ids: list[int] | None = None,
) -> None:
    """Track-only spend as the 'ai_helper' source (one cost line for the tool)."""
    from app.services.usage import record_usage

    ref: dict = {
        "table_id": run.table_id,
        "ai_helper_run_id": run.id,
        "row_id": row_id,
    }
    if column_id is not None:
        ref["column_id"] = column_id
    if column_ids is not None:
        ref["column_ids"] = column_ids
    await record_usage(
        db,
        user_id=run.created_by_id,
        provider_code=code,
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        source="ai_helper",
        source_ref=ref,
    )


# ---------- per_output engine: one cell per call ----------


async def _process_cell(db: AsyncSession, run_id: int, cell_id: int) -> None:
    cell = await db.get(AiHelperCell, cell_id)
    if cell is None or cell.state != "pending":
        return  # already processed / redelivery
    run = await db.get(AiHelperRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    if run.status == "cancelled":
        cell.state = "skipped"
        await _bump_by(db, run_id, "skipped", 1)
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    row_values = await _row_values(db, cell.row_id)
    target_current = row_values.get(cell.column_id, "")

    output = next(
        (o for o in effective_outputs(run) if o["column_id"] == cell.column_id), None
    )
    if output is None:
        # Config drift (output/column removed) — don't clobber; fail the cell.
        await _fail_cell(
            db, run_id, cell, target_current, "No matching output for this column."
        )
        return

    variables = _variables_for(run, row_values)
    rendered, _missing = render_template(output["prompt"] or run.prompt, variables)

    try:
        text_out, code, model, pt, ct = await _call_ai(db, run, rendered)
    except (ProviderError, ProviderNotConfigured) as e:
        await _fail_cell(db, run_id, cell, target_current, str(e))
        return
    except Exception as e:  # noqa: BLE001 — never strand the run
        await _fail_cell(db, run_id, cell, target_current, f"Unexpected error: {e}")
        return

    new_value = _value_to_write(run, output, text_out, row_values)
    await _upsert_cell_value(db, cell.row_id, cell.column_id, new_value)
    cell.old_value = target_current
    cell.new_value = new_value
    cell.state = "done"
    await _bump_by(db, run_id, "done", 1)
    await db.commit()

    await _record_usage(
        db, run, code, model, pt, ct, cell.row_id, column_id=cell.column_id
    )
    await _finalize_if_done(db, run_id)


# ---------- structured engine: one call per row, routed to its outputs ----------


async def _process_row(db: AsyncSession, run_id: int, row_id: int) -> None:
    run = await db.get(AiHelperRun, run_id)
    if run is None or run.status in ("done", "failed"):
        return
    cells = (
        (
            await db.execute(
                select(AiHelperCell).where(
                    AiHelperCell.run_id == run_id,
                    AiHelperCell.row_id == row_id,
                    AiHelperCell.state == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    if not cells:
        return  # already processed / redelivery
    if run.status == "cancelled":
        for c in cells:
            c.state = "skipped"
        await _bump_by(db, run_id, "skipped", len(cells))
        await db.commit()
        await _finalize_if_done(db, run_id)
        return

    outputs = effective_outputs(run)
    by_col = {o["column_id"]: o for o in outputs}
    row_values = await _row_values(db, row_id)
    variables = _variables_for(run, row_values)
    rendered = render_template(run.prompt or "", variables)[0] + build_structured_suffix(
        outputs
    )

    try:
        text_out, code, model, pt, ct = await _call_ai(db, run, rendered)
    except (ProviderError, ProviderNotConfigured) as e:
        await _fail_row(db, run_id, cells, row_values, str(e))
        return
    except Exception as e:  # noqa: BLE001 — never strand the run
        await _fail_row(db, run_id, cells, row_values, f"Unexpected error: {e}")
        return

    # The call happened; route its JSON to each output cell.
    obj = extract_json_object(text_out)
    done_n = skipped_n = failed_n = 0
    for c in cells:
        current = row_values.get(c.column_id, "")
        output = by_col.get(c.column_id)
        if obj is None:
            c.state = "failed"
            c.old_value = current
            c.error = "Model did not return valid JSON."
            failed_n += 1
            continue
        if output is None or output["key"] not in obj:
            # Missing key ⇒ leave the column untouched.
            c.state = "skipped"
            c.old_value = current
            skipped_n += 1
            continue
        raw = obj[output["key"]]
        text_val = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
        new_value = _value_to_write(run, output, text_val, row_values)
        await _upsert_cell_value(db, row_id, c.column_id, new_value)
        c.old_value = current
        c.new_value = new_value
        c.state = "done"
        done_n += 1

    await _bump_by(db, run_id, "done", done_n)
    await _bump_by(db, run_id, "skipped", skipped_n)
    await _bump_by(db, run_id, "failed", failed_n)
    await db.commit()

    await _record_usage(
        db, run, code, model, pt, ct, row_id, column_ids=[c.column_id for c in cells]
    )
    await _finalize_if_done(db, run_id)


async def _fail_row(
    db: AsyncSession,
    run_id: int,
    cells: list[AiHelperCell],
    row_values: dict[int, str],
    error: str,
) -> None:
    """Whole-row failure (the single structured call errored) — no spend."""
    for c in cells:
        c.state = "failed"
        c.old_value = row_values.get(c.column_id, "")
        c.error = error[:500]
    await _bump_by(db, run_id, "failed", len(cells))
    await db.commit()
    await _finalize_if_done(db, run_id)


# ---------- counters / finalize / resume ----------


async def _fail_cell(
    db: AsyncSession, run_id: int, cell: AiHelperCell, old_value: str, error: str
) -> None:
    cell.state = "failed"
    cell.old_value = old_value
    cell.error = error[:500]
    await _bump_by(db, run_id, "failed", 1)
    await db.commit()
    await _finalize_if_done(db, run_id)


async def _bump_by(db: AsyncSession, run_id: int, field: str, n: int) -> None:
    """Atomic counter bump (+n) + progress stamp. ``field`` is a trusted literal."""
    if field not in ("done", "failed", "skipped"):
        raise ValueError(field)
    if n <= 0:
        return
    col = getattr(AiHelperRun, field)
    await db.execute(
        update(AiHelperRun)
        .where(AiHelperRun.id == run_id)
        .values({field: col + n, "last_progress_at": _now()})
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
    """Re-enqueue a run's pending work (manual Resume / retry-failed / stall)."""
    run = await db.get(AiHelperRun, run_id)
    if run is None or run.status != "running":
        return
    run.last_progress_at = _now()
    await db.commit()

    if effective_engine(run) == "structured":
        rows = (
            (
                await db.execute(
                    select(AiHelperCell.row_id)
                    .where(
                        AiHelperCell.run_id == run_id,
                        AiHelperCell.state == "pending",
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            await _finalize_if_done(db, run_id)
            return
        for rid in rows:
            process_row.delay(run_id, rid)
        return

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
