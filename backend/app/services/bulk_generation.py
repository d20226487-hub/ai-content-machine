"""Resolve a single output cell: variables -> provider call -> persist result.

The Celery task in app/tasks/bulk_generation.py wraps this so calls don't block
the web request. Status transitions:
  * before enqueue  -> 'generating' (set synchronously by the API endpoint)
  * task succeeds   -> 'generated' with value, model_used, generated_at
  * task fails      -> 'failed' with error text
"""
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BulkGenerationRun,
    BulkTable,
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    Prompt,
    PromptVersion,
)
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import ProviderNotConfigured, get_provider
from app.services.ai_assist import first_enabled_provider_code
from app.services.error_log import log_error
from app.services.generation_limits import (
    is_truncated,
    load_generation_limits,
    resolve_max_output_tokens,
)
from app.services.prompts import render_template


async def _load_column(db: AsyncSession, column_id: int) -> BulkTableColumn:
    col = (
        await db.execute(
            select(BulkTableColumn).where(BulkTableColumn.id == column_id)
        )
    ).scalar_one()
    return col


async def _load_row_cells_by_column(
    db: AsyncSession, row_id: int
) -> dict[int, str]:
    """Return {column_id: value} for every non-empty cell in this row."""
    rows = (
        await db.execute(
            select(BulkTableCell).where(BulkTableCell.row_id == row_id)
        )
    ).scalars().all()
    return {c.column_id: (c.value or "") for c in rows}


async def _resolve_prompt_template(
    db: AsyncSession, prompt_id: int, version_number: int | None
) -> str:
    """Return the prompt content for the given version, or current if version is None."""
    if version_number is not None:
        v = (
            await db.execute(
                select(PromptVersion).where(
                    PromptVersion.prompt_id == prompt_id,
                    PromptVersion.version_number == version_number,
                )
            )
        ).scalar_one_or_none()
        if v is None:
            raise ValueError(f"Prompt version {version_number} not found")
        return v.content

    # Use current version
    p = (await db.execute(select(Prompt).where(Prompt.id == prompt_id))).scalar_one_or_none()
    if p is None or p.current_version_id is None:
        raise ValueError(f"Prompt {prompt_id} has no current version")
    v = (
        await db.execute(
            select(PromptVersion).where(PromptVersion.id == p.current_version_id)
        )
    ).scalar_one()
    return v.content


async def _ensure_cell(
    db: AsyncSession, row_id: int, column_id: int
) -> BulkTableCell:
    cell = (
        await db.execute(
            select(BulkTableCell).where(
                BulkTableCell.row_id == row_id,
                BulkTableCell.column_id == column_id,
            )
        )
    ).scalar_one_or_none()
    if cell is None:
        cell = BulkTableCell(row_id=row_id, column_id=column_id, status="empty")
        db.add(cell)
        await db.flush()
    return cell


async def mark_cell_generating(
    db: AsyncSession, row_id: int, column_id: int
) -> int:
    """Synchronously flip the cell to 'generating' before enqueueing the task.
    Returns the cell id."""
    cell = await _ensure_cell(db, row_id, column_id)
    cell.status = "generating"
    cell.error = None
    # Clear the previous run's stop reason so a retry doesn't keep showing a
    # stale "truncated" badge while it regenerates.
    cell.finish_reason = None
    await db.commit()
    return cell.id


async def _is_run_cancelled(db: AsyncSession, run_id: int) -> bool:
    """Fast pre-check: is this run cancelled? Avoids loading the full
    row when all we need is the status."""
    res = await db.execute(
        text("SELECT status FROM bulk_generation_runs WHERE id = :id"),
        {"id": run_id},
    )
    row = res.first()
    return row is not None and row[0] == "cancelled"


async def _claim_generating_cell(
    db: AsyncSession, row_id: int, column_id: int, error: str
) -> bool:
    """Flip one cell ``'generating' -> 'failed'`` iff it is still generating.

    Returns True only when THIS call performed the transition. Two settlers can
    race for a cancelled run — the cancel endpoint's bulk sweep and this
    per-task pre-check — and row-level locking on the guarded UPDATE lets
    exactly one of them win. The winner counts the cell (bumps ``skipped``); the
    loser gets False and counts nothing, so the run tallies can't overshoot
    ``total`` (and, more importantly, never undershoot it and strand the run).
    """
    row = (
        await db.execute(
            text(
                "UPDATE bulk_table_cells "
                "SET status = 'failed', error = :err, finish_reason = NULL "
                "WHERE row_id = :r AND column_id = :c AND status = 'generating' "
                "RETURNING id"
            ),
            {"err": error[:2000], "r": row_id, "c": column_id},
        )
    ).first()
    await db.commit()
    return row is not None


async def _bump_run_counter(
    db: AsyncSession, run_id: int, *, field: str
) -> None:
    """Atomically increment one of ``done`` / ``failed`` / ``skipped`` on
    the run row, then mark the run done + stamp finished_at if all cells
    have been accounted for. The last-worker-finishes pattern keeps the
    finished_at honest (not the cancel click).

    The two SQL statements run in one transaction so a peer worker
    bumping a different counter in parallel either sees our increment
    as already applied or our terminal flip as already taken. Neither
    statement guards against the run id not existing (callers verify
    that upstream)."""
    assert field in ("done", "failed", "skipped"), field
    # Inline the column name — it's whitelisted above, no SQL injection
    # risk, and we want a single round-trip.
    await db.execute(
        text(
            f"UPDATE bulk_generation_runs "
            f"SET {field} = {field} + 1 WHERE id = :id"
        ),
        {"id": run_id},
    )
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
    # Same idea for cancelled-and-now-fully-drained: stamp finished_at
    # so the UI shows a real elapsed time on the detail page.
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


async def generate_one_cell(
    db: AsyncSession,
    *,
    table_id: int,
    row_id: int,
    column_id: int,
    override_provider_code: str | None = None,
    override_model: str | None = None,
    run_id: int | None = None,
) -> None:
    """Do the work and persist either success or failure. Caller commits.

    `override_provider_code` + `override_model`: queue-wide override. When
    both are non-None, they replace the per-column settings for this call.
    Validated together at the API layer; we just trust the pair here.

    `run_id`: BulkGenerationRun the cell belongs to. If the run has been
    cancelled before we reach this cell, we short-circuit (mark the cell
    failed with a "Cancelled before completion" note, bump run.skipped)
    instead of doing a provider call. Legacy callers (none in tree
    today, but kept for safety) can omit run_id and the bookkeeping is
    just skipped.
    """
    # Cancellation pre-check. Cheap query, no provider cost.
    if run_id is not None and await _is_run_cancelled(db, run_id):
        # Guarded settle: the cancel endpoint may have already swept this cell
        # in bulk. Count it toward `skipped` only if WE are the one that flips
        # it out of 'generating', so the same cell can't be double-counted.
        if await _claim_generating_cell(
            db, row_id, column_id, "Cancelled before completion"
        ):
            await _bump_run_counter(db, run_id, field="skipped")
        return

    col = await _load_column(db, column_id)

    # Sanity: must be an output column with a prompt assignment.
    if col.kind != "output" or col.prompt_id is None:
        await _write_failure(
            db, row_id, column_id, "Column has no prompt assigned"
        )
        if run_id is not None:
            await _bump_run_counter(db, run_id, field="failed")
        return

    try:
        template = await _resolve_prompt_template(
            db, col.prompt_id, col.prompt_version_number
        )
    except ValueError as e:
        await _write_failure(db, row_id, column_id, str(e))
        if run_id is not None:
            await _bump_run_counter(db, run_id, field="failed")
        return

    row_values = await _load_row_cells_by_column(db, row_id)

    # Build the variables dict from the column's variable_map (var_name -> source_column_id)
    variables: dict[str, str] = {}
    for var_name, source_col_id in (col.variable_map or {}).items():
        variables[var_name] = row_values.get(int(source_col_id), "")

    rendered, _missing = render_template(template, variables)

    # Resolution order:
    #   1. Queue-wide override (if both fields set on this run)
    #   2. Per-column provider_code/model
    #   3. Fallback: first-enabled provider + its default model
    code = (
        override_provider_code
        or col.provider_code
        or await first_enabled_provider_code(db)
    )
    if not code:
        await _write_failure(
            db, row_id, column_id, "No AI provider is enabled. Configure one in Settings."
        )
        if run_id is not None:
            await _bump_run_counter(db, run_id, field="failed")
        return

    try:
        provider = await get_provider(db, code)
    except ProviderNotConfigured as e:
        await _write_failure(db, row_id, column_id, str(e))
        if run_id is not None:
            await _bump_run_counter(db, run_id, field="failed")
        return

    # Load the provider row for rate-limit settings + per-column model override fallback.
    from app.db.models import Provider  # local import to avoid an import cycle
    provider_row = (
        await db.execute(select(Provider).where(Provider.code == code))
    ).scalar_one()

    chosen_model = override_model or col.model or provider_row.default_model

    # Cached read; the per-column override is applied at the call site below.
    gen_limits = await load_generation_limits(db)

    from app.services import grounding_cache
    from app.services.rate_limit import get_rate_limiter
    from app.services.retry import call_with_retry

    # Grounding memo: a grounded call carries a per-request surcharge, so cache
    # its result keyed by the exact rendered prompt + model. An identical re-run
    # or a duplicate-input row reuses it and pays nothing. Non-grounded columns
    # never touch the cache.
    grounded = bool(col.grounding)
    gc_key = (
        grounding_cache.cache_key(rendered, chosen_model, col.grounding)
        if grounded
        else None
    )
    cached_result = await grounding_cache.get_cached(db, gc_key) if gc_key else None

    if cached_result is not None:
        result = cached_result
    else:
        limiter = get_rate_limiter()
        try:
            async with limiter.acquire(
                provider_code=code,
                max_concurrency=provider_row.max_concurrency,
                requests_per_minute=provider_row.requests_per_minute,
                inter_request_delay_ms=provider_row.inter_request_delay_ms,
            ):
                result = await call_with_retry(
                    provider,
                    prompt=rendered,
                    model=chosen_model,
                    params=GenerationParams(
                        temperature=0.7,
                        max_output_tokens=resolve_max_output_tokens(
                            col.max_output_tokens, gen_limits
                        ),
                        thinking_budget=gen_limits.thinking_budget,
                        # Per-column grounding (null = off). Only the Vertex
                        # Gemini path acts on it; other providers ignore it.
                        grounding=col.grounding,
                    ),
                    retry_max_attempts=provider_row.retry_max_attempts,
                    backoff_base_ms=provider_row.backoff_base_ms,
                    backoff_jitter_ms=provider_row.backoff_jitter_ms,
                    respect_retry_after=provider_row.respect_retry_after,
                )
        except ProviderError as e:
            await _write_failure(db, row_id, column_id, str(e))
            await _log_provider_failure(
                db,
                table_id=table_id,
                row_id=row_id,
                column_id=column_id,
                provider_code=code,
                model=chosen_model,
                error=e,
            )
            if run_id is not None:
                await _bump_run_counter(db, run_id, field="failed")
            return
        except Exception as e:  # last-resort
            await _write_failure(db, row_id, column_id, f"Unexpected error: {e}")
            await log_error(
                db,
                source="worker",
                category="unhandled",
                message=f"{type(e).__name__}: {e}",
                provider=code,
                context={
                    "table_id": table_id,
                    "row_id": row_id,
                    "column_id": column_id,
                    "model": chosen_model,
                },
                resource_type="cell",
                resource_id=f"{row_id}:{column_id}",
            )
            if run_id is not None:
                await _bump_run_counter(db, run_id, field="failed")
            return
        # Cache the fresh grounded result so identical re-runs skip the paid call.
        if gc_key is not None:
            await grounding_cache.put_cached(
                db, gc_key, provider_code=code, model=chosen_model, result=result
            )

    cell = await _ensure_cell(db, row_id, column_id)
    cell.value = result.text
    cell.status = "generated"
    cell.error = None
    # Record WHY the model stopped. Discarding this is what made hitting the
    # token ceiling invisible: a cell cut off mid-article looked exactly like a
    # complete one. A truncated reply is still a usable partial, so it keeps
    # the "generated" status — the UI badges it off this field instead.
    cell.finish_reason = (result.finish_reason or None)
    cell.model_used = result.model
    cell.generated_at = datetime.now(timezone.utc)
    # A fresh generation invalidates any prior translations of this cell —
    # the source they translated no longer exists.
    cell.translations = None
    # Grounding provenance for THIS text: the sources the model cited, stamped
    # with when they were fetched. None (cleared) when the column isn't grounded
    # or the provider returned no metadata — same lifecycle as translations.
    if result.grounding:
        cell.grounding_sources = {
            **result.grounding,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        cell.grounding_sources = None

    # Bump the parent table's updated_at so the Library list re-sorts.
    table = (
        await db.execute(select(BulkTable).where(BulkTable.id == table_id))
    ).scalar_one_or_none()
    if table is not None:
        table.name = table.name  # touch so onupdate fires

    await db.commit()

    # Track-only spend log (#9) — ONLY when we actually called the provider; a
    # cache hit is free. Attribute the spend to the table owner so it shows up
    # under the right user in /users. Best-effort.
    if cached_result is None:
        from app.services.usage import (  # local import: avoid cycle
            record_grounding_surcharge,
            record_usage,
        )

        await record_usage(
            db,
            user_id=table.created_by_id if table is not None else None,
            provider_code=code,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            source="bulk_cell",
            source_ref={
                "table_id": table_id,
                "row_id": row_id,
                "column_id": column_id,
            },
        )
        # Flat per-request surcharge for the Google Search grounding tool.
        if grounded:
            await record_grounding_surcharge(
                db,
                user_id=table.created_by_id if table is not None else None,
                provider_code=code,
                model=result.model,
                source_ref={
                    "table_id": table_id,
                    "row_id": row_id,
                    "column_id": column_id,
                },
            )

    if run_id is not None:
        await _bump_run_counter(db, run_id, field="done")


async def _write_failure(
    db: AsyncSession, row_id: int, column_id: int, error: str
) -> None:
    cell = await _ensure_cell(db, row_id, column_id)
    cell.status = "failed"
    cell.error = error[:2000]
    cell.finish_reason = None
    await db.commit()


async def _log_provider_failure(
    db: AsyncSession,
    *,
    table_id: int,
    row_id: int,
    column_id: int,
    provider_code: str,
    model: str | None,
    error: ProviderError,
) -> None:
    table = (
        await db.execute(select(BulkTable).where(BulkTable.id == table_id))
    ).scalar_one_or_none()
    user_id = table.created_by_id if table is not None else None

    await log_error(
        db,
        source="worker",
        category="provider_error",
        message=str(error),
        user_id=user_id,
        provider=provider_code,
        status_code=getattr(error, "status_code", None),
        context={
            "table_id": table_id,
            "row_id": row_id,
            "column_id": column_id,
            "model": model,
            "raw": getattr(error, "raw", None),
        },
        resource_type="cell",
        resource_id=f"{row_id}:{column_id}",
    )
