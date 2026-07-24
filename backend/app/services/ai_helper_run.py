"""AI Helper runs — validate + seed a per-cell run, plus its lifecycle controls.

The endpoint calls ``create_run`` (validates the prompt/mapping/config, seeds one
``AiHelperCell`` per selected row, sets the run ``running``) then fans out the
per-cell Celery tasks. Cancel / resume / retry-failed / revert mirror the
link-fix tool. ``preview`` gives the pre-run cost estimate for the confirm gate.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AiHelperCell,
    AiHelperRun,
    BulkTableCell,
    BulkTableColumn,
    BulkTableRow,
    Provider,
)
from app.schemas.ai_helper import (
    AiHelperCellRead,
    AiHelperPreview,
    AiHelperRunCreate,
    AiHelperRunDetail,
    AiHelperRunRead,
)
from app.services.ai_assist import first_enabled_provider_code
from app.services.ai_helper_slice import slice_first_words
from app.services.generation_limits import (
    load_generation_limits,
    resolve_max_output_tokens,
)
from app.services.pricing import compute_cost_usd, load_pricing
from app.services.prompts import extract_variables, render_template

_PREVIEW_SAMPLE = 25  # rows sampled to estimate the average input size
_CHARS_PER_TOKEN = 4  # rough token estimate


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


# ----- read views -----


def _run_to_read(run: AiHelperRun) -> AiHelperRunRead:
    return AiHelperRunRead(
        id=run.id,
        table_id=run.table_id,
        status=run.status,
        mode=run.mode,
        name=run.name,
        target_column_id=run.target_column_id,
        total=run.total,
        done=run.done,
        failed=run.failed,
        skipped=run.skipped,
        reverted_at=run.reverted_at,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _cell_to_read(c: AiHelperCell) -> AiHelperCellRead:
    return AiHelperCellRead(
        id=c.id,
        row_id=c.row_id,
        row_position=c.row_position,
        column_id=c.column_id,
        state=c.state,
        old_value=c.old_value,
        new_value=c.new_value,
        error=c.error,
    )


async def get_run_detail(
    db: AsyncSession, run_id: int, page: int, page_size: int
) -> AiHelperRunDetail:
    run = await db.get(AiHelperRun, run_id)
    if run is None:
        raise _not_found()
    items_total = (
        await db.execute(
            select(func.count())
            .select_from(AiHelperCell)
            .where(AiHelperCell.run_id == run_id)
        )
    ).scalar_one()
    items = (
        (
            await db.execute(
                select(AiHelperCell)
                .where(AiHelperCell.run_id == run_id)
                .order_by(AiHelperCell.row_position.asc(), AiHelperCell.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    base = _run_to_read(run)
    return AiHelperRunDetail(
        **base.model_dump(),
        prompt=run.prompt,
        variable_map=run.variable_map or {},
        provider_code=run.provider_code,
        model=run.model,
        input_scope=run.input_scope,
        input_pct=run.input_pct,
        error=run.error,
        items=[_cell_to_read(i) for i in items],
        items_total=int(items_total),
        items_page=page,
        items_page_size=page_size,
    )


# ----- validation + create -----


async def _table_column_ids(db: AsyncSession, table_id: int) -> set[int]:
    return set(
        (
            await db.execute(
                select(BulkTableColumn.id).where(BulkTableColumn.table_id == table_id)
            )
        )
        .scalars()
        .all()
    )


async def _rows_for(
    db: AsyncSession, table_id: int, row_ids: list[int]
) -> list[tuple[int, int]]:
    """[(row_id, position)] for the run, ordered. Empty row_ids = all rows."""
    stmt = select(BulkTableRow.id, BulkTableRow.position).where(
        BulkTableRow.table_id == table_id
    )
    if row_ids:
        stmt = stmt.where(BulkTableRow.id.in_(row_ids))
    stmt = stmt.order_by(BulkTableRow.position, BulkTableRow.id)
    return [(rid, pos) for rid, pos in (await db.execute(stmt)).all()]


def _validate(payload: AiHelperRunCreate, col_ids: set[int]) -> None:
    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise _bad_request("A prompt is required.")
    if payload.mode not in ("read", "edit"):
        raise _bad_request("Mode must be 'read' or 'edit'.")

    # variable_map values must be real columns; every {{var}} must be mapped.
    for var, cid in (payload.variable_map or {}).items():
        if int(cid) not in col_ids:
            raise _bad_request(f"Mapped column for {{{{{var}}}}} is not in this table.")
    unmapped = [v for v in extract_variables(prompt) if v not in (payload.variable_map or {})]
    if unmapped:
        raise _bad_request(
            "Map every prompt variable to a column. Unmapped: "
            + ", ".join(unmapped)
        )

    if payload.target_column_id not in col_ids:
        raise _bad_request("The target column is not in this table.")
    mapped_cols = {int(c) for c in (payload.variable_map or {}).values()}
    if payload.mode == "edit" and payload.target_column_id not in mapped_cols:
        raise _bad_request(
            "Edit mode rewrites the target column, so it must also be one of the "
            "prompt's input columns (e.g. map {{Content}} to it)."
        )

    if payload.input_scope not in ("full", "first_pct"):
        raise _bad_request("Input scope must be 'full' or 'first_pct'.")
    if payload.input_scope == "first_pct":
        if not payload.input_pct or not (1 <= payload.input_pct <= 100):
            raise _bad_request("First-N% slicing needs a percent between 1 and 100.")
        if payload.slice_column_id is None:
            raise _bad_request("Pick which column to slice.")
        if payload.mode == "edit" and payload.slice_column_id != payload.target_column_id:
            raise _bad_request(
                "In Edit mode the sliced column must be the target column "
                "(the edited slice is spliced back into it)."
            )
        if payload.mode == "read" and payload.slice_column_id not in mapped_cols:
            raise _bad_request("The sliced column must be one of the mapped inputs.")


async def create_run(
    db: AsyncSession,
    table_id: int,
    payload: AiHelperRunCreate,
    user_id: int | None,
) -> tuple[AiHelperRun, list[int]]:
    """Validate, seed one cell per selected row, mark the run running. Returns
    (run, cell_ids); the caller fans out the per-cell tasks."""
    col_ids = await _table_column_ids(db, table_id)
    _validate(payload, col_ids)

    rows = await _rows_for(db, table_id, payload.row_ids)
    if not rows:
        raise _bad_request("No rows to process.")

    now = datetime.now(timezone.utc)
    run = AiHelperRun(
        table_id=table_id,
        created_by_id=user_id,
        status="running",
        mode=payload.mode,
        name=(payload.name or "").strip() or None,
        prompt=payload.prompt.strip(),
        prompt_id=payload.prompt_id,
        variable_map={k: int(v) for k, v in (payload.variable_map or {}).items()},
        target_column_id=payload.target_column_id,
        provider_code=(payload.provider_code or "").strip() or None,
        model=(payload.model or "").strip() or None,
        max_output_tokens=payload.max_output_tokens,
        input_scope=payload.input_scope,
        input_pct=payload.input_pct if payload.input_scope == "first_pct" else None,
        slice_column_id=(
            payload.slice_column_id if payload.input_scope == "first_pct" else None
        ),
        row_ids=[rid for rid, _ in rows],
        total=len(rows),
        started_at=now,
        last_progress_at=now,
    )
    db.add(run)
    await db.flush()

    db.add_all(
        [
            AiHelperCell(
                run_id=run.id,
                row_id=rid,
                row_position=pos,
                column_id=payload.target_column_id,
                state="pending",
            )
            for rid, pos in rows
        ]
    )
    await db.commit()
    await db.refresh(run)

    cell_ids = (
        (
            await db.execute(
                select(AiHelperCell.id).where(AiHelperCell.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    return run, list(cell_ids)


# ----- controls -----


async def cancel_run(db: AsyncSession, run_id: int) -> AiHelperRunDetail:
    run = await db.get(AiHelperRun, run_id)
    if run is None:
        raise _not_found()
    if run.status == "running":
        now = datetime.now(timezone.utc)
        res = await db.execute(
            update(AiHelperCell)
            .where(AiHelperCell.run_id == run_id, AiHelperCell.state == "pending")
            .values(state="skipped")
        )
        run.skipped = (run.skipped or 0) + (res.rowcount or 0)
        run.status = "cancelled"
        run.finished_at = now
        await db.commit()
    return await get_run_detail(db, run_id, 1, 50)


async def retry_failed(db: AsyncSession, run_id: int) -> None:
    """Reset failed cells to pending and re-arm the run (caller re-enqueues)."""
    run = await db.get(AiHelperRun, run_id)
    if run is None:
        raise _not_found()
    if run.status not in ("done", "failed", "cancelled"):
        raise _bad_request("Run is still in progress.")
    failed = (
        await db.execute(
            select(func.count())
            .select_from(AiHelperCell)
            .where(AiHelperCell.run_id == run_id, AiHelperCell.state == "failed")
        )
    ).scalar_one()
    if not failed:
        raise _bad_request("No failed cells to retry.")
    await db.execute(
        update(AiHelperCell)
        .where(AiHelperCell.run_id == run_id, AiHelperCell.state == "failed")
        .values(state="pending", error=None)
    )
    run.failed = max(0, run.failed - int(failed))
    run.status = "running"
    run.finished_at = None
    run.last_progress_at = datetime.now(timezone.utc)
    await db.commit()


async def revert_run(db: AsyncSession, run_id: int) -> AiHelperRunDetail:
    """Restore each done cell's pre-write value (drift-guarded), stamp reverted."""
    run = await db.get(AiHelperRun, run_id)
    if run is None:
        raise _not_found()
    if run.reverted_at is not None:
        return await get_run_detail(db, run_id, 1, 50)  # idempotent

    cells = (
        (
            await db.execute(
                select(AiHelperCell).where(
                    AiHelperCell.run_id == run_id, AiHelperCell.state == "done"
                )
            )
        )
        .scalars()
        .all()
    )
    for cell in cells:
        current = (
            await db.execute(
                select(BulkTableCell.value).where(
                    BulkTableCell.row_id == cell.row_id,
                    BulkTableCell.column_id == cell.column_id,
                )
            )
        ).scalar_one_or_none()
        # Only revert cells we still own (no manual/regenerated edit since).
        if current != cell.new_value:
            continue
        await db.execute(
            update(BulkTableCell)
            .where(
                BulkTableCell.row_id == cell.row_id,
                BulkTableCell.column_id == cell.column_id,
            )
            .values(value=(cell.old_value or ""), translations=None)
        )
    run.reverted_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_run_detail(db, run_id, 1, 50)


# ----- cost preview -----


async def preview(
    db: AsyncSession, table_id: int, payload: AiHelperRunCreate
) -> AiHelperPreview:
    """Matched-row count + a best-effort upper-bound cost for the confirm gate."""
    col_ids = await _table_column_ids(db, table_id)
    _validate(payload, col_ids)
    rows = await _rows_for(db, table_id, payload.row_ids)
    matched = len(rows)

    code = (payload.provider_code or "").strip() or await first_enabled_provider_code(db)
    provider_configured = bool(code)
    model = (payload.model or "").strip() or None
    if code and not model:
        provider_row = (
            await db.execute(select(Provider).where(Provider.code == code))
        ).scalar_one_or_none()
        model = provider_row.default_model if provider_row else None

    if matched == 0 or not code or not model:
        return AiHelperPreview(
            matched_rows=matched,
            provider_code=code,
            model=model,
            provider_configured=provider_configured,
        )

    # Sample a handful of rows, render the prompt, estimate avg input tokens.
    sample_ids = [rid for rid, _ in rows[:_PREVIEW_SAMPLE]]
    values = await _row_values_bulk(db, sample_ids)
    total_chars = 0
    for rid in sample_ids:
        rv = values.get(rid, {})
        variables: dict[str, str] = {}
        for var, cid in (payload.variable_map or {}).items():
            v = rv.get(int(cid), "")
            if (
                payload.input_scope == "first_pct"
                and payload.slice_column_id == int(cid)
                and payload.input_pct
            ):
                v, _ = slice_first_words(v, int(payload.input_pct))
            variables[var] = v
        rendered, _ = render_template(payload.prompt, variables)
        total_chars += len(rendered)
    avg_input_tokens = int((total_chars / max(1, len(sample_ids))) / _CHARS_PER_TOKEN)

    gen_limits = await load_generation_limits(db)
    out_tokens = resolve_max_output_tokens(payload.max_output_tokens, gen_limits)

    rates = await load_pricing(db)
    per_row = compute_cost_usd(
        rates,
        provider_code=code,
        model=model,
        prompt_tokens=avg_input_tokens,
        completion_tokens=out_tokens,
    )
    est = float(per_row) * matched if per_row is not None else None

    return AiHelperPreview(
        matched_rows=matched,
        provider_code=code,
        model=model,
        est_cost_usd=round(est, 4) if est is not None else None,
        est_input_tokens_avg=avg_input_tokens,
        provider_configured=provider_configured,
    )


async def _row_values_bulk(
    db: AsyncSession, row_ids: list[int]
) -> dict[int, dict[int, str]]:
    """{row_id: {column_id: value}} for the given rows."""
    out: dict[int, dict[int, str]] = {rid: {} for rid in row_ids}
    if not row_ids:
        return out
    for rid, cid, val in (
        await db.execute(
            select(BulkTableCell.row_id, BulkTableCell.column_id, BulkTableCell.value)
            .where(BulkTableCell.row_id.in_(row_ids))
        )
    ).all():
        out.setdefault(rid, {})[cid] = val or ""
    return out
