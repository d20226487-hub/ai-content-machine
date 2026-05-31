"""Bulk publish runs: API surface.

Run lifecycle (mirrors the bulk_generation pattern):
  POST /publish/bulk            → creates a run + enqueues seed task
  GET  /publish/runs            → list (admin/manager)
  GET  /publish/runs/{id}       → detail (config + counters + by-domain)
  POST /publish/runs/{id}/pause | resume | cancel | rerun-failed

Mapping memo (auto-prefill the modal next time):
  GET    /publish/mappings/{table_id}/single/{domain_id}/{profile_name}
  DELETE /publish/mappings/{table_id}/single/{domain_id}/{profile_name}
  GET    /publish/mappings/{table_id}/multi
  DELETE /publish/mappings/{table_id}/multi

Profile name uses '-' as a placeholder for "no profile" in the URL since
empty path segments don't work; the API normalizes '-' → ''.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete as sa_delete, func, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.models import (
    BulkPublishRun,
    BulkTable,
    BulkTableColumn,
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
    ByDomainStat,
    PublishMapping,
    RunRename,
)
from app.tasks.publish_bulk import (
    publish_one_bulk_row as publish_one_bulk_row_task,
    seed_publish_run as seed_publish_run_task,
)

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


async def _column_belongs_to_table(
    db: AsyncSession, *, column_id: int, table_id: int
) -> bool:
    col = await db.get(BulkTableColumn, column_id)
    return col is not None and col.table_id == table_id


@router.post("/bulk", response_model=BulkRunDetail, status_code=status.HTTP_201_CREATED)
async def create_bulk_publish_run(
    payload: BulkPublishRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> BulkRunDetail:
    table = await db.get(BulkTable, payload.table_id)
    if table is None:
        raise HTTPException(status_code=404, detail="Table not found")

    if not payload.field_to_column:
        raise HTTPException(
            status_code=400,
            detail="field_to_column mapping is required (map at least the required publish fields to bulk columns)",
        )

    domain_id: int | None = None
    profile = ""
    domain_column_id: int | None = None
    profile_column_id: int | None = None

    if payload.mode == "single":
        # Pydantic validator already enforced domain_id is present.
        domain = await db.get(Domain, payload.domain_id)  # type: ignore[arg-type]
        if domain is None or domain.deleted_at is not None:
            # Trashed domains are not pickable as publish targets.
            raise HTTPException(status_code=404, detail="Domain not found")
        domain_id = domain.id
        profile = _norm_profile(payload.profile_name)
        # Validate operation vs cms_type per-CMS at run creation so the user
        # gets a clear rejection instead of every row failing one by one.
        # Multi mode validates per-row in resolve_row_target since each row
        # may point at a different cms_type.
        if payload.operation == "upsert" and domain.cms_type != "custom":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Upsert is supported only for Custom CMS domains. "
                    f"{domain.name!r} is configured as {domain.cms_type}; "
                    "use Create or Update instead."
                ),
            )
        if payload.operation == "update" and domain.cms_type == "wordpress":
            # WP update relies on find_post → PATCH, which needs the lookup
            # column. Same payload shape now used for Custom CMS (see the
            # branch below) so the UI can present a uniform "Find existing
            # posts by" picker across CMS types.
            if payload.lookup_kind is None or payload.lookup_column_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "WordPress Update mode requires lookup_kind + "
                        "lookup_column_id (the column holding the post id "
                        "or slug for each row)."
                    ),
                )
        if payload.operation == "update" and domain.cms_type == "custom":
            # Custom CMS update needs the upstream post id in the outgoing
            # body. Two payload shapes are accepted to keep saved mappings
            # from the old UI working:
            #   * NEW: lookup_kind="id" + lookup_column_id pointing at the
            #     column with the id. Mirrors WP's shape so the frontend
            #     can render one "Find existing posts by" picker.
            #   * LEGACY: field_to_column["id"] = <column> (no lookup_*).
            #     This was the only option before 2026-05-23 and lives on
            #     in saved mappings.
            # The bridge that normalizes the two shapes to a single
            # `field_to_column["id"]` runs unconditionally below (after
            # the mode-specific block) so multi-mode runs benefit too.
            has_lookup = (
                payload.lookup_kind == "id" and payload.lookup_column_id is not None
            )
            has_legacy_id = "id" in payload.field_to_column
            if not has_lookup and not has_legacy_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Custom CMS Update mode requires picking the column "
                        "that holds each row's upstream post id (use the "
                        "'Find existing posts by' panel)."
                    ),
                )
            if payload.lookup_kind not in (None, "id"):
                # WP supports slug-based lookup, Custom CMS doesn't (the
                # upstream `__add_content=1` finder doesn't accept an
                # old_slug parameter). Reject early with a clear hint
                # rather than letting the run fail row-by-row.
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Custom CMS Update can only look up by 'id' for now. "
                        "Looking up by slug needs upstream support that the "
                        "current __add_content endpoint doesn't expose."
                    ),
                )
    else:
        # Multi mode: domain_column_id required (Pydantic enforced). The
        # profile column is optional — it's only consumed for WordPress
        # rows; Custom CMS rows ignore it (no profile concept). A mixed-
        # CMS table can set the profile column and the resolver will use
        # it for WP rows and skip it for Custom rows.
        if payload.domain_column_id is None:
            raise HTTPException(
                status_code=400, detail="domain_column_id is required in multi mode"
            )
        if not await _column_belongs_to_table(
            db, column_id=payload.domain_column_id, table_id=table.id
        ):
            raise HTTPException(
                status_code=400,
                detail="domain_column_id does not belong to this table",
            )
        if payload.profile_column_id is not None:
            if not await _column_belongs_to_table(
                db, column_id=payload.profile_column_id, table_id=table.id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="profile_column_id does not belong to this table",
                )
        domain_column_id = payload.domain_column_id
        profile_column_id = payload.profile_column_id

    # Optional per-row language column. Works in BOTH single and multi
    # mode: each row reads its language from the cell, the value is
    # lowercase+trim normalized, and must match one of the resolved
    # domain's `languages[]`. In single mode the domain is run-level; in
    # multi mode it's per-row. Empty cells fail the row in strict mode.
    language_column_id: int | None = None
    if payload.language_column_id is not None:
        if not await _column_belongs_to_table(
            db, column_id=payload.language_column_id, table_id=table.id
        ):
            raise HTTPException(
                status_code=400,
                detail="language_column_id does not belong to this table",
            )
        language_column_id = payload.language_column_id

    # Update mode: ensure the lookup column exists on this table. The
    # WP-vs-Custom split was already done above; here we just bind the
    # column when present and apply the Custom-CMS bridge.
    lookup_kind = payload.lookup_kind
    lookup_column_id = payload.lookup_column_id
    if payload.operation == "update" and payload.lookup_column_id is not None:
        if not await _column_belongs_to_table(
            db,
            column_id=payload.lookup_column_id,
            table_id=table.id,
        ):
            raise HTTPException(
                status_code=400,
                detail="lookup_column_id does not belong to this table",
            )

    # Custom-CMS-bridge: when the user supplies lookup_kind="id" +
    # lookup_column_id (the new unified UI), mirror that into the legacy
    # field_to_column["id"] so the existing Custom CMS worker path keeps
    # working without changes. Multi-mode runs can target both WP and
    # Custom rows — the extra `id` key on WP rows is harmless (WP REST
    # ignores unknown body keys, and WP Update reads its lookup straight
    # from lookup_column_id, not from the body).
    if (
        payload.operation == "update"
        and payload.lookup_kind == "id"
        and payload.lookup_column_id is not None
        and "id" not in payload.field_to_column
    ):
        payload.field_to_column = {
            **payload.field_to_column,
            "id": payload.lookup_column_id,
        }

    run = BulkPublishRun(
        table_id=table.id,
        mode=payload.mode,
        domain_id=domain_id,
        profile_name=profile,
        domain_column_id=domain_column_id,
        profile_column_id=profile_column_id,
        language_column_id=language_column_id,
        language=payload.language,
        row_filter=payload.row_filter,
        selection=payload.selection,
        cell_filter=payload.cell_filter,
        field_to_column={k: int(v) for k, v in payload.field_to_column.items()},
        back_fill={k: int(v) for k, v in payload.back_fill.items()},
        status="queued",
        created_by_id=actor.id,
        operation=payload.operation,
        lookup_kind=lookup_kind,
        lookup_column_id=lookup_column_id,
        on_slug_conflict=payload.on_slug_conflict,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Persist the mapping memo so the modal pre-fills next time.
    if payload.save_mapping:
        await _save_mapping(
            db,
            table_id=table.id,
            mode=payload.mode,
            domain_id=domain_id,
            profile_name=profile if payload.mode == "single" else None,
            domain_column_id=domain_column_id,
            profile_column_id=profile_column_id,
            field_to_column=run.field_to_column,
            back_fill=run.back_fill,
            language=payload.language,
            actor_id=actor.id,
            operation=payload.operation,
            lookup_kind=lookup_kind,
            lookup_column_id=lookup_column_id,
            language_column_id=language_column_id,
            on_slug_conflict=payload.on_slug_conflict,
        )

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


@router.patch("/runs/{run_id}", response_model=BulkRunDetail)
async def rename_run(
    run_id: int,
    payload: RunRename,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> BulkRunDetail:
    """Set/clear a run's display name. Blank → fall back to the id label."""
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    n = (payload.name or "").strip()
    run.name = n or None
    await db.commit()
    await db.refresh(run)
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
    seed_publish_run_task.delay(run_id)
    return detail


@router.post(
    "/runs/{run_id}/rerun-failed",
    response_model=BulkRunDetail,
)
async def rerun_failed_rows(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> BulkRunDetail:
    """Re-attempt the failed rows of a terminal run in-place.

    No new BulkPublishRun is created. The existing run flips back to
    ``running``; its ``failed`` counter is decremented by the count being
    retried; ``finished_at`` and ``error`` are cleared; and a child task is
    enqueued directly for each failed row (the seed task is bypassed —
    candidate computation would otherwise still exclude these rows because
    they already have a 'failed' PublishJob).

    The old failed PublishJob rows for those rows are deleted before the
    new attempts go out. Without this the run-detail per-row table mixed
    the old failures with the new in-flight rows and confused users —
    the run-level counters are the source of truth, and the deeper audit
    trail is captured by error_logs (which we don't touch here).
    """
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")

    if run.status not in ("done", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot rerun failed rows while run is {run.status}; wait for it to finish first.",
        )

    # In single mode the original run's domain must still exist; in multi
    # mode each row resolves its own, so we just need the column refs.
    if run.mode == "single" and run.domain_id is None:
        raise HTTPException(
            status_code=409,
            detail="Original run's domain has been deleted; cannot rerun.",
        )
    if run.mode == "multi" and run.domain_column_id is None:
        raise HTTPException(
            status_code=409,
            detail="Original run's domain column has been deleted; cannot rerun.",
        )

    failed_rows = (
        await db.execute(
            select(PublishJob.source_ref).where(
                PublishJob.source_kind == "bulk_row",
                PublishJob.status == "failed",
                PublishJob.source_ref["run_id"].astext == str(run.id),
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

    # Exclude rows that already have a non-failed job for this run (defensive —
    # shouldn't happen if the run reached a terminal state, but a manual DB
    # edit or a partially-applied retry could leave one behind).
    if row_ids:
        active = (
            await db.execute(
                select(PublishJob.source_ref).where(
                    PublishJob.source_kind == "bulk_row",
                    PublishJob.status.in_(("posted", "posting")),
                    PublishJob.source_ref["run_id"].astext == str(run.id),
                )
            )
        ).all()
        blocked: set[int] = set()
        for (sref,) in active:
            try:
                blocked.add(int((sref or {}).get("row_id")))
            except (TypeError, ValueError):
                continue
        row_ids = [r for r in row_ids if r not in blocked]

    if not row_ids:
        raise HTTPException(status_code=409, detail="No failed rows to rerun.")

    # Wipe the old failed publish_jobs for the rows we're about to retry so
    # the run-detail per-row table only shows the new in-flight attempt.
    # We intentionally only delete `failed` jobs for this run + these rows
    # — posted/posting rows are untouched (and aren't in row_ids anyway via
    # the earlier filter). The error_logs row that mirrored each failure
    # stays put — that's the long-form audit trail.
    str_row_ids = [str(r) for r in row_ids]
    await db.execute(
        sa_delete(PublishJob).where(
            PublishJob.source_kind == "bulk_row",
            PublishJob.status == "failed",
            PublishJob.source_ref["run_id"].astext == str(run.id),
            PublishJob.source_ref["row_id"].astext.in_(str_row_ids),
        )
    )

    # Reopen the run. Decrement the failed counter by the number of rows we're
    # about to retry so the finalizer math (done + failed + skipped >= total)
    # works out when the new attempts complete.
    run.status = "running"
    run.failed = max(0, run.failed - len(row_ids))
    run.finished_at = None
    run.error = None
    await db.commit()
    await db.refresh(run)

    for row_id in row_ids:
        publish_one_bulk_row_task.delay(run.id, row_id)

    return await _to_detail(db, run)


_TERMINAL_RUN_STATUSES = ("done", "failed", "cancelled")


@router.delete(
    "/runs/completed",
    status_code=status.HTTP_200_OK,
)
async def clear_completed_runs(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> dict:
    """Delete every BulkPublishRun in a terminal state (done | failed | cancelled).

    Child PublishJob rows referencing each run via source_ref->>'run_id' are
    deleted first (no FK, so we do it manually). In-flight runs (queued /
    running / paused) are left alone — cancel them first.
    """
    run_ids = (
        await db.execute(
            select(BulkPublishRun.id).where(
                BulkPublishRun.status.in_(_TERMINAL_RUN_STATUSES)
            )
        )
    ).scalars().all()
    if not run_ids:
        return {"deleted": 0}

    str_ids = [str(i) for i in run_ids]
    await db.execute(
        sa_delete(PublishJob).where(
            PublishJob.source_kind == "bulk_row",
            PublishJob.source_ref["run_id"].astext.in_(str_ids),
        )
    )
    result = await db.execute(
        sa_delete(BulkPublishRun).where(BulkPublishRun.id.in_(run_ids))
    )
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> Response:
    """Delete a terminal BulkPublishRun and its child publish_jobs.

    PublishJob rows reference the run via source_ref->>'run_id' (no FK), so
    we explicitly delete them first.
    """
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    if run.status not in _TERMINAL_RUN_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete a run while it is {run.status!r}. Cancel it first.",
        )
    await db.execute(
        sa_delete(PublishJob).where(
            PublishJob.source_kind == "bulk_row",
            PublishJob.source_ref["run_id"].astext == str(run.id),
        )
    )
    await db.delete(run)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


# ---------- mapping memo ----------

@router.get(
    "/mappings/{table_id}/single/{domain_id}/{profile_name}",
    response_model=PublishMapping,
)
async def get_mapping_single(
    table_id: int,
    domain_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db),
) -> PublishMapping:
    profile = _decode_url_profile(profile_name)
    row = (
        await db.execute(
            select(BulkTablePublishMapping).where(
                BulkTablePublishMapping.table_id == table_id,
                BulkTablePublishMapping.mode == "single",
                BulkTablePublishMapping.domain_id == domain_id,
                BulkTablePublishMapping.profile_name == profile,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return PublishMapping()
    return PublishMapping(
        field_to_column=row.field_to_column or {},
        back_fill=row.back_fill or {},
        language=row.language,
        operation=row.operation,
        lookup_kind=row.lookup_kind,
        lookup_column_id=row.lookup_column_id,
        on_slug_conflict=row.on_slug_conflict,
    )


@router.delete(
    "/mappings/{table_id}/single/{domain_id}/{profile_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mapping_single(
    table_id: int,
    domain_id: int,
    profile_name: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    profile = _decode_url_profile(profile_name)
    row = (
        await db.execute(
            select(BulkTablePublishMapping).where(
                BulkTablePublishMapping.table_id == table_id,
                BulkTablePublishMapping.mode == "single",
                BulkTablePublishMapping.domain_id == domain_id,
                BulkTablePublishMapping.profile_name == profile,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/mappings/{table_id}/multi",
    response_model=PublishMapping,
)
async def get_mapping_multi(
    table_id: int,
    db: AsyncSession = Depends(get_db),
) -> PublishMapping:
    row = (
        await db.execute(
            select(BulkTablePublishMapping).where(
                BulkTablePublishMapping.table_id == table_id,
                BulkTablePublishMapping.mode == "multi",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return PublishMapping()
    return PublishMapping(
        field_to_column=row.field_to_column or {},
        back_fill=row.back_fill or {},
        language=row.language,
        domain_column_id=row.domain_column_id,
        profile_column_id=row.profile_column_id,
        language_column_id=row.language_column_id,
        operation=row.operation,
        lookup_kind=row.lookup_kind,
        lookup_column_id=row.lookup_column_id,
        on_slug_conflict=row.on_slug_conflict,
    )


@router.delete(
    "/mappings/{table_id}/multi",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mapping_multi(
    table_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = (
        await db.execute(
            select(BulkTablePublishMapping).where(
                BulkTablePublishMapping.table_id == table_id,
                BulkTablePublishMapping.mode == "multi",
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- helpers ----------


async def _save_mapping(
    db: AsyncSession,
    *,
    table_id: int,
    mode: str,
    domain_id: int | None,
    profile_name: str | None,
    domain_column_id: int | None,
    profile_column_id: int | None,
    field_to_column: dict[str, int],
    back_fill: dict[str, int],
    language: str | None,
    actor_id: int | None,
    operation: str = "create",
    lookup_kind: str | None = None,
    lookup_column_id: int | None = None,
    language_column_id: int | None = None,
    on_slug_conflict: str = "create",
) -> None:
    """Upsert a mapping memo. Two shapes coexist:
      single mode: keyed on (table_id, mode='single', domain_id, profile_name)
      multi mode:  keyed on (table_id, mode='multi')
    Partial unique indexes enforce both shapes.
    """
    if mode == "single":
        existing = (
            await db.execute(
                select(BulkTablePublishMapping).where(
                    BulkTablePublishMapping.table_id == table_id,
                    BulkTablePublishMapping.mode == "single",
                    BulkTablePublishMapping.domain_id == domain_id,
                    BulkTablePublishMapping.profile_name == (profile_name or ""),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = BulkTablePublishMapping(
                table_id=table_id,
                mode="single",
                domain_id=domain_id,
                profile_name=profile_name or "",
            )
            db.add(existing)
    else:
        existing = (
            await db.execute(
                select(BulkTablePublishMapping).where(
                    BulkTablePublishMapping.table_id == table_id,
                    BulkTablePublishMapping.mode == "multi",
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = BulkTablePublishMapping(
                table_id=table_id,
                mode="multi",
            )
            db.add(existing)
        existing.domain_column_id = domain_column_id
        existing.profile_column_id = profile_column_id
        existing.language_column_id = language_column_id

    existing.field_to_column = dict(field_to_column)
    existing.back_fill = dict(back_fill)
    existing.language = language
    existing.operation = operation
    existing.lookup_kind = lookup_kind
    existing.lookup_column_id = lookup_column_id
    existing.on_slug_conflict = on_slug_conflict
    existing.updated_by_id = actor_id
    await db.commit()


def _to_summary(
    run: BulkPublishRun,
    *,
    domain_name: str | None,
    table_name: str | None,
) -> BulkRunSummary:
    return BulkRunSummary(
        id=run.id,
        name=run.name,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        table_id=run.table_id,
        mode=run.mode,  # type: ignore[arg-type]
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
        operation=run.operation,  # type: ignore[arg-type]
        lookup_kind=run.lookup_kind,  # type: ignore[arg-type]
        lookup_column_id=run.lookup_column_id,
        language_column_id=run.language_column_id,
        on_slug_conflict=run.on_slug_conflict,  # type: ignore[arg-type]
    )


async def _by_domain_summary(
    db: AsyncSession, run: BulkPublishRun
) -> list[ByDomainStat]:
    """Group this run's publish_jobs by domain and count outcomes.

    Cheap aggregation query — at most one row per domain that ever got a job
    in this run. For multi-mode runs with hundreds of domains it's still a
    single GROUP BY on a small index.
    """
    stmt = sa_text(
        """
        SELECT
            pj.domain_id,
            d.name AS domain_name,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE pj.status = 'posted') AS posted,
            COUNT(*) FILTER (WHERE pj.status = 'failed') AS failed
        FROM publish_jobs pj
        LEFT JOIN domains d ON d.id = pj.domain_id
        WHERE pj.source_kind = 'bulk_row'
          AND pj.source_ref->>'run_id' = :run_id
        GROUP BY pj.domain_id, d.name
        ORDER BY total DESC, domain_name NULLS LAST
        """
    )
    rows = (await db.execute(stmt, {"run_id": str(run.id)})).all()
    return [
        ByDomainStat(
            domain_id=r[0],
            domain_name=r[1],
            total=int(r[2]),
            posted=int(r[3]),
            failed=int(r[4]),
        )
        for r in rows
    ]


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

    by_domain: list[ByDomainStat] = []
    if run.mode == "multi":
        by_domain = await _by_domain_summary(db, run)

    base = _to_summary(run, domain_name=domain_name, table_name=table_name)
    return BulkRunDetail(
        **base.model_dump(),
        row_filter=run.row_filter,  # type: ignore[arg-type]
        selection=run.selection,
        cell_filter=run.cell_filter,  # type: ignore[arg-type]
        field_to_column=run.field_to_column or {},
        back_fill=run.back_fill or {},
        domain_column_id=run.domain_column_id,
        profile_column_id=run.profile_column_id,
        by_domain=by_domain,
    )
