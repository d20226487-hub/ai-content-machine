"""Bulk publish runs: API surface.

Run lifecycle (mirrors the bulk_generation pattern):
  POST /publish/bulk            → creates a run + enqueues seed task
  GET  /publish/runs            → list (admin/manager)
  GET  /publish/runs/{id}       → detail (config + counters)
  POST /publish/runs/{id}/pause | resume | cancel

Mapping memo (auto-prefill the modal next time):
  GET    /publish/mappings/{table_id}/{domain_id}/{profile_name}
  DELETE /publish/mappings/{table_id}/{domain_id}/{profile_name}

Profile name uses '-' as a placeholder for "no profile" in the URL since
empty path segments don't work; the API normalizes '-' → ''.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.models import (
    BulkPublishRun,
    BulkTable,
    BulkTablePublishMapping,
    Domain,
    PublishJob,
    User,
)
from app.db.session import get_db
from app.schemas.publish import (
    BulkPublishRequest,
    BulkRunDetail,
    BulkRunListResponse,
    BulkRunSummary,
    PublishMapping,
)
from app.tasks.publish_bulk import seed_publish_run as seed_publish_run_task

router = APIRouter(
    prefix="/publish",
    tags=["publish-bulk"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


def _norm_profile(name: str | None) -> str:
    return name or ""


def _decode_url_profile(name: str) -> str:
    """URL placeholder '-' means empty profile."""
    return "" if name == "-" else name


@router.post("/bulk", response_model=BulkRunDetail, status_code=status.HTTP_201_CREATED)
async def create_bulk_publish_run(
    payload: BulkPublishRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> BulkRunDetail:
    table = await db.get(BulkTable, payload.table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")
    domain = await db.get(Domain, payload.domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    if not payload.field_to_column:
        raise HTTPException(
            status_code=400,
            detail="field_to_column mapping is required (map at least the required publish fields to bulk columns)",
        )

    profile = _norm_profile(payload.profile_name)

    run = BulkPublishRun(
        table_id=table.id,
        domain_id=domain.id,
        profile_name=profile,
        language=payload.language,
        row_filter=payload.row_filter,
        selection=payload.selection,
        cell_filter=payload.cell_filter,
        field_to_column={k: int(v) for k, v in payload.field_to_column.items()},
        back_fill={k: int(v) for k, v in payload.back_fill.items()},
        status="queued",
        created_by_id=actor.id,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Persist the mapping memo so the modal pre-fills next time.
    if payload.save_mapping:
        existing = await db.get(
            BulkTablePublishMapping, (table.id, domain.id, profile)
        )
        if existing is None:
            existing = BulkTablePublishMapping(
                table_id=table.id,
                domain_id=domain.id,
                profile_name=profile,
            )
            db.add(existing)
        existing.field_to_column = run.field_to_column
        existing.back_fill = run.back_fill
        existing.language = payload.language
        existing.updated_by_id = actor.id
        await db.commit()

    # Kick the seed Celery task. Synchronous .delay() on the broker is fine —
    # it only enqueues the message; the actual scan + child enqueueing happens
    # in the worker.
    seed_publish_run_task.delay(run.id)

    return await _to_detail(db, run)


@router.get("/runs", response_model=BulkRunListResponse)
async def list_runs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    table_id: int | None = None,
    domain_id: int | None = None,
) -> BulkRunListResponse:
    base = select(BulkPublishRun, Domain.name, BulkTable.name).join(
        Domain, Domain.id == BulkPublishRun.domain_id, isouter=True
    ).join(BulkTable, BulkTable.id == BulkPublishRun.table_id, isouter=True)
    count_stmt = select(func.count(BulkPublishRun.id))

    conditions = []
    if status_filter:
        conditions.append(BulkPublishRun.status == status_filter)
    if table_id is not None:
        conditions.append(BulkPublishRun.table_id == table_id)
    if domain_id is not None:
        conditions.append(BulkPublishRun.domain_id == domain_id)
    for c in conditions:
        base = base.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()
    base = (
        base.order_by(BulkPublishRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(base)).all()
    items = [
        _to_summary(r[0], domain_name=r[1], table_name=r[2]) for r in rows
    ]
    return BulkRunListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/runs/{run_id}", response_model=BulkRunDetail)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)) -> BulkRunDetail:
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    return await _to_detail(db, run)


async def _set_status(
    db: AsyncSession, run_id: int, *, allowed_from: set[str], next_status: str
) -> BulkRunDetail:
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    if run.status not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from {run.status} to {next_status}",
        )
    run.status = next_status
    if next_status in ("done", "cancelled", "failed") and run.finished_at is None:
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return await _to_detail(db, run)


@router.post("/runs/{run_id}/pause", response_model=BulkRunDetail)
async def pause_run(run_id: int, db: AsyncSession = Depends(get_db)) -> BulkRunDetail:
    return await _set_status(
        db, run_id, allowed_from={"queued", "running"}, next_status="paused"
    )


@router.post("/runs/{run_id}/resume", response_model=BulkRunDetail)
async def resume_run(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> BulkRunDetail:
    detail = await _set_status(
        db, run_id, allowed_from={"paused"}, next_status="running"
    )
    # Re-enqueue the seed task — it'll skip rows already processed and
    # only re-enqueue children for rows that haven't reached a terminal state.
    seed_publish_run_task.delay(run_id)
    return detail


@router.post(
    "/runs/{run_id}/rerun-failed",
    response_model=BulkRunDetail,
    status_code=status.HTTP_201_CREATED,
)
async def rerun_failed_rows(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> BulkRunDetail:
    """Create a new run targeting only the rows that failed in this run.

    Inherits the original run's domain, profile, language, mapping, and back-fill.
    """
    src = await db.get(BulkPublishRun, run_id)
    if src is None:
        raise HTTPException(status_code=404, detail="Not found")
    if src.domain_id is None:
        raise HTTPException(
            status_code=409,
            detail="Original run's domain has been deleted; cannot rerun.",
        )

    failed_rows = (
        await db.execute(
            select(PublishJob.source_ref).where(
                PublishJob.source_kind == "bulk_row",
                PublishJob.status == "failed",
                PublishJob.source_ref["run_id"].astext == str(src.id),
            )
        )
    ).all()
    row_ids: list[int] = []
    seen: set[int] = set()
    for (sref,) in failed_rows:
        try:
            rid = int((sref or {}).get("row_id"))
        except (TypeError, ValueError):
            continue
        if rid not in seen:
            seen.add(rid)
            row_ids.append(rid)

    if not row_ids:
        raise HTTPException(status_code=409, detail="No failed rows to rerun.")

    new_run = BulkPublishRun(
        table_id=src.table_id,
        domain_id=src.domain_id,
        profile_name=src.profile_name or "",
        language=src.language,
        row_filter="selected",
        selection={"row_ids": row_ids},
        cell_filter="all",
        field_to_column=dict(src.field_to_column or {}),
        back_fill=dict(src.back_fill or {}),
        status="queued",
        created_by_id=actor.id,
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)

    seed_publish_run_task.delay(new_run.id)
    return await _to_detail(db, new_run)


@router.post("/runs/{run_id}/cancel", response_model=BulkRunDetail)
async def cancel_run(
    run_id: int, db: AsyncSession = Depends(get_db)
) -> BulkRunDetail:
    return await _set_status(
        db,
        run_id,
        allowed_from={"queued", "running", "paused"},
        next_status="cancelled",
    )


@router.get(
    "/mappings/{table_id}/{domain_id}/{profile_name}",
    response_model=PublishMapping,
)
async def get_mapping(
    table_id: int,
    domain_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db),
) -> PublishMapping:
    profile = _decode_url_profile(profile_name)
    row = await db.get(BulkTablePublishMapping, (table_id, domain_id, profile))
    if row is None:
        return PublishMapping()
    return PublishMapping(
        field_to_column=row.field_to_column or {},
        back_fill=row.back_fill or {},
        language=row.language,
    )


@router.delete(
    "/mappings/{table_id}/{domain_id}/{profile_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mapping(
    table_id: int,
    domain_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    profile = _decode_url_profile(profile_name)
    row = await db.get(BulkTablePublishMapping, (table_id, domain_id, profile))
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- helpers ----

def _to_summary(
    run: BulkPublishRun,
    *,
    domain_name: str | None,
    table_name: str | None,
) -> BulkRunSummary:
    return BulkRunSummary(
        id=run.id,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        table_id=run.table_id,
        domain_id=run.domain_id,
        domain_name=domain_name,
        table_name=table_name,
        profile_name=run.profile_name or None,
        language=run.language,
        status=run.status,  # type: ignore[arg-type]
        total=run.total,
        done=run.done,
        failed=run.failed,
        skipped=run.skipped,
        error=run.error,
        created_by_id=run.created_by_id,
    )


async def _to_detail(db: AsyncSession, run: BulkPublishRun) -> BulkRunDetail:
    domain_name = None
    table_name = None
    if run.domain_id is not None:
        d = await db.get(Domain, run.domain_id)
        if d is not None:
            domain_name = d.name
    if run.table_id is not None:
        t = await db.get(BulkTable, run.table_id)
        if t is not None:
            table_name = t.name
    base = _to_summary(run, domain_name=domain_name, table_name=table_name)
    return BulkRunDetail(
        **base.model_dump(),
        row_filter=run.row_filter,  # type: ignore[arg-type]
        selection=run.selection,
        cell_filter=run.cell_filter,  # type: ignore[arg-type]
        field_to_column=run.field_to_column or {},
        back_fill=run.back_fill or {},
    )
