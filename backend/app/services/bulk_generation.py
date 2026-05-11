"""Resolve a single output cell: variables -> provider call -> persist result.

The Celery task in app/tasks/bulk_generation.py wraps this so calls don't block
the web request. Status transitions:
  * before enqueue  -> 'generating' (set synchronously by the API endpoint)
  * task succeeds   -> 'generated' with value, model_used, generated_at
  * task fails      -> 'failed' with error text
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
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
    await db.commit()
    return cell.id


async def generate_one_cell(
    db: AsyncSession,
    *,
    table_id: int,
    row_id: int,
    column_id: int,
    override_provider_code: str | None = None,
    override_model: str | None = None,
) -> None:
    """Do the work and persist either success or failure. Caller commits.

    `override_provider_code` + `override_model`: queue-wide override. When
    both are non-None, they replace the per-column settings for this call.
    Validated together at the API layer; we just trust the pair here.
    """
    col = await _load_column(db, column_id)

    # Sanity: must be an output column with a prompt assignment.
    if col.kind != "output" or col.prompt_id is None:
        await _write_failure(
            db, row_id, column_id, "Column has no prompt assigned"
        )
        return

    try:
        template = await _resolve_prompt_template(
            db, col.prompt_id, col.prompt_version_number
        )
    except ValueError as e:
        await _write_failure(db, row_id, column_id, str(e))
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
        return

    try:
        provider = await get_provider(db, code)
    except ProviderNotConfigured as e:
        await _write_failure(db, row_id, column_id, str(e))
        return

    # Load the provider row for rate-limit settings + per-column model override fallback.
    from app.db.models import Provider  # local import to avoid an import cycle
    provider_row = (
        await db.execute(select(Provider).where(Provider.code == code))
    ).scalar_one()

    chosen_model = override_model or col.model or provider_row.default_model

    from app.services.rate_limit import get_rate_limiter
    from app.services.retry import call_with_retry

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
                params=GenerationParams(temperature=0.7, max_output_tokens=2048),
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
        return

    cell = await _ensure_cell(db, row_id, column_id)
    cell.value = result.text
    cell.status = "generated"
    cell.error = None
    cell.model_used = result.model
    cell.generated_at = datetime.now(timezone.utc)

    # Bump the parent table's updated_at so the Library list re-sorts.
    table = (
        await db.execute(select(BulkTable).where(BulkTable.id == table_id))
    ).scalar_one_or_none()
    if table is not None:
        table.name = table.name  # touch so onupdate fires

    await db.commit()

    # Track-only spend log (#9). Attribute the spend to the table owner so
    # it shows up under the right user in /users. Best-effort.
    from app.services.usage import record_usage  # local import: avoid cycle
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


async def _write_failure(
    db: AsyncSession, row_id: int, column_id: int, error: str
) -> None:
    cell = await _ensure_cell(db, row_id, column_id)
    cell.status = "failed"
    cell.error = error[:2000]
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
