"""Bulk Custom-CMS cache clear/warm runs.

A run is created from a set of selected domain ids + an action; only active
Custom-CMS domains become items (WordPress publishes via Autotool and has no
cache endpoints — those ids are excluded and counted in ``skipped_unsupported``).
A Celery worker then fans out one ``process_one_item`` per item, fires the
chosen cache endpoint(s) via the domain's CmsClient (reusing its stored
credentials), and bumps the run counters. The run finalises (``done``) when
``done + failed + skipped >= total``.

Controls: Cancel (queued items → skipped; run → cancelled) and Retry-failed
(failed items → queued; run → running again on the SAME run). Parallel fan-out
(no sequential chaining) — each domain is independent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.registry import UnsupportedCms, get_cms_client
from app.db.models import Domain, DomainCacheRun, DomainCacheRunItem
from app.schemas.domain_cache import (
    MAX_CACHE_RUN_DOMAINS,
    DomainCacheRunDetail,
    DomainCacheRunItemRead,
    DomainCacheRunRead,
    DomainCacheRunsPage,
)

_BUMP_FIELDS = {"done", "failed"}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


# ----- read views -----


def _run_to_read(run: DomainCacheRun) -> DomainCacheRunRead:
    return DomainCacheRunRead(
        id=run.id,
        action=run.action,
        status=run.status,
        total=run.total,
        done=run.done,
        failed=run.failed,
        skipped=run.skipped,
        skipped_unsupported=run.skipped_unsupported,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _item_to_read(it: DomainCacheRunItem) -> DomainCacheRunItemRead:
    return DomainCacheRunItemRead(
        id=it.id,
        domain_id=it.domain_id,
        domain_name=it.domain_name,
        base_url=it.base_url,
        status=it.status,
        clear_status_code=it.clear_status_code,
        warm_status_code=it.warm_status_code,
        detail=it.detail,
        elapsed_ms=it.elapsed_ms,
        created_at=it.created_at,
    )


async def list_runs(
    db: AsyncSession, page: int, page_size: int
) -> DomainCacheRunsPage:
    total = (
        await db.execute(select(func.count()).select_from(DomainCacheRun))
    ).scalar_one()
    runs = (
        (
            await db.execute(
                select(DomainCacheRun)
                .order_by(DomainCacheRun.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return DomainCacheRunsPage(
        items=[_run_to_read(r) for r in runs],
        total=int(total),
        page=page,
        page_size=page_size,
    )


async def get_run_detail(
    db: AsyncSession, run_id: int, page: int, page_size: int
) -> DomainCacheRunDetail:
    run = await db.get(DomainCacheRun, run_id)
    if run is None:
        raise _not_found()
    items_total = (
        await db.execute(
            select(func.count())
            .select_from(DomainCacheRunItem)
            .where(DomainCacheRunItem.run_id == run_id)
        )
    ).scalar_one()
    items = (
        (
            await db.execute(
                select(DomainCacheRunItem)
                .where(DomainCacheRunItem.run_id == run_id)
                .order_by(DomainCacheRunItem.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    base = _run_to_read(run)
    return DomainCacheRunDetail(
        **base.model_dump(),
        error=run.error,
        items=[_item_to_read(i) for i in items],
        items_total=int(items_total),
        items_page=page,
        items_page_size=page_size,
    )


# ----- create -----


async def create_run(
    db: AsyncSession,
    domain_ids: list[int],
    action: str,
    user_id: int | None,
) -> DomainCacheRun:
    """Resolve the selection to active Custom-CMS domains, insert a queued run
    with one item per domain. The caller enqueues the seed task.

    Non-Custom / trashed / missing ids are excluded and recorded in
    ``skipped_unsupported``. Raises 400 if nothing usable remains."""
    rows = (
        (
            await db.execute(
                select(Domain).where(
                    Domain.id.in_(domain_ids),
                    Domain.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {d.id: d for d in rows}
    # Preserve the caller's order; keep only active Custom-CMS domains.
    custom = [
        by_id[i]
        for i in domain_ids
        if i in by_id and by_id[i].cms_type == "custom"
    ]
    skipped_unsupported = len(domain_ids) - len(custom)

    if not custom:
        raise _bad_request(
            "None of the selected domains are Custom CMS sites. Cache "
            "clear/warm only applies to Custom CMS domains (WordPress sites "
            "publish via Autotool)."
        )
    if len(custom) > MAX_CACHE_RUN_DOMAINS:
        raise _bad_request(
            f"Too many domains ({len(custom)}) for one run "
            f"(max {MAX_CACHE_RUN_DOMAINS})."
        )

    run = DomainCacheRun(
        action=action,
        status="queued",
        total=len(custom),
        skipped_unsupported=skipped_unsupported,
        created_by_id=user_id,
    )
    db.add(run)
    await db.flush()
    for d in custom:
        db.add(
            DomainCacheRunItem(
                run_id=run.id,
                domain_id=d.id,
                domain_name=d.name,
                base_url=d.base_url,
                status="queued",
            )
        )
    await db.commit()
    await db.refresh(run)
    return run


# ----- run lifecycle (called by Celery) -----


async def start_run(db: AsyncSession, run_id: int) -> list[int]:
    """Flip a queued/running run to 'running' and return ALL its queued item
    ids for parallel fan-out. Returns [] for terminal runs (and finalises a
    zero-item run)."""
    run = await db.get(DomainCacheRun, run_id)
    if run is None or run.status in ("cancelled", "done", "failed"):
        return []
    if run.status == "queued" and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
    run.status = "running"
    await db.commit()

    if run.total == 0:
        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return []

    return await queued_item_ids(db, run_id)


async def queued_item_ids(db: AsyncSession, run_id: int) -> list[int]:
    """All 'queued' item ids — but only while the run is still 'running' (so
    cancel/finish stops further fan-out and the watchdog won't re-arm a
    terminal run)."""
    run = await db.get(DomainCacheRun, run_id)
    if run is None or run.status != "running":
        return []
    return list(
        (
            await db.execute(
                select(DomainCacheRunItem.id)
                .where(
                    DomainCacheRunItem.run_id == run_id,
                    DomainCacheRunItem.status == "queued",
                )
                .order_by(DomainCacheRunItem.id.asc())
            )
        )
        .scalars()
        .all()
    )


async def _bump(db: AsyncSession, *, run_id: int, field: str) -> None:
    """Atomically increment done/failed and finalise when the total is reached."""
    if field not in _BUMP_FIELDS:
        raise ValueError(f"_bump: field must be one of {_BUMP_FIELDS}, got {field!r}")
    await db.execute(
        text(f"UPDATE domain_cache_runs SET {field} = {field} + 1 WHERE id = :id"),
        {"id": run_id},
    )
    await db.execute(
        text(
            "UPDATE domain_cache_runs "
            "SET status = 'done', finished_at = now() "
            "WHERE id = :id AND status = 'running' "
            "AND done + failed + skipped >= total AND total > 0"
        ),
        {"id": run_id},
    )
    await db.commit()


async def process_one_item(db: AsyncSession, run_id: int, item_id: int) -> str:
    """Fire one domain's cache action and record the outcome.

    Idempotent via a guarded 'queued'->'running' claim, so a redelivered or
    watchdog-re-enqueued task is a no-op once the item has been claimed."""
    run = await db.get(DomainCacheRun, run_id)
    if run is None or run.status in ("cancelled", "done", "failed"):
        return "run_terminal"

    now = datetime.now(timezone.utc)
    claim = await db.execute(
        update(DomainCacheRunItem)
        .where(
            DomainCacheRunItem.id == item_id,
            DomainCacheRunItem.status == "queued",
        )
        .values(status="running", updated_at=now)
    )
    await db.commit()
    if (claim.rowcount or 0) != 1:
        return "not_queued"

    item = await db.get(DomainCacheRunItem, item_id)

    # The domain may have been hard-deleted since the run was created (FK
    # SET NULL nulls item.domain_id). We need the live row for its decrypted
    # credentials, so a missing/non-custom domain fails the item cleanly.
    domain = (
        await db.get(Domain, item.domain_id) if item.domain_id is not None else None
    )
    if domain is None or domain.cms_type != "custom":
        item.status = "failed"
        item.detail = "Domain is no longer available as a Custom CMS site."
        item.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await _bump(db, run_id=run_id, field="failed")
        return item.status

    clear_code: int | None = None
    warm_code: int | None = None
    elapsed_total = 0
    parts: list[str] = []
    ok = True

    try:
        client = get_cms_client(domain)
    except UnsupportedCms as e:
        item.status = "failed"
        item.detail = str(e)
        item.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await _bump(db, run_id=run_id, field="failed")
        return item.status

    if run.action in ("clear", "clear_and_warm"):
        cr = await client.clear_cache()
        clear_code = cr.status_code
        elapsed_total += cr.elapsed_ms or 0
        parts.append(f"clear: {cr.detail}")
        ok = ok and cr.ok
    if run.action in ("warm", "clear_and_warm"):
        wr = await client.warm_cache()
        warm_code = wr.status_code
        elapsed_total += wr.elapsed_ms or 0
        parts.append(f"warm: {wr.detail}")
        ok = ok and wr.ok

    item.status = "done" if ok else "failed"
    item.clear_status_code = clear_code
    item.warm_status_code = warm_code
    item.detail = "; ".join(parts) if parts else None
    item.elapsed_ms = elapsed_total or None
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await _bump(db, run_id=run_id, field="done" if ok else "failed")
    return item.status


# ----- controls -----


async def cancel_run(db: AsyncSession, run_id: int) -> DomainCacheRunDetail:
    run = await db.get(DomainCacheRun, run_id)
    if run is None:
        raise _not_found()
    if run.status in ("queued", "running"):
        now = datetime.now(timezone.utc)
        res = await db.execute(
            update(DomainCacheRunItem)
            .where(
                DomainCacheRunItem.run_id == run_id,
                DomainCacheRunItem.status == "queued",
            )
            .values(status="skipped", updated_at=now)
        )
        run.skipped = (run.skipped or 0) + (res.rowcount or 0)
        run.status = "cancelled"
        run.finished_at = now
        await db.commit()
    return await get_run_detail(db, run_id, 1, 50)


async def retry_failed(db: AsyncSession, run_id: int) -> list[int]:
    """Reset failed items to 'queued' on the SAME run and re-arm it. Returns the
    requeued item ids for the caller to enqueue (via the seed task)."""
    run = await db.get(DomainCacheRun, run_id)
    if run is None:
        raise _not_found()
    if run.status not in ("done", "failed", "cancelled"):
        raise _bad_request("Run is still in progress.")
    failed_ids = (
        (
            await db.execute(
                select(DomainCacheRunItem.id).where(
                    DomainCacheRunItem.run_id == run_id,
                    DomainCacheRunItem.status == "failed",
                )
            )
        )
        .scalars()
        .all()
    )
    if not failed_ids:
        raise _bad_request("No failed items to retry.")
    now = datetime.now(timezone.utc)
    await db.execute(
        update(DomainCacheRunItem)
        .where(
            DomainCacheRunItem.run_id == run_id,
            DomainCacheRunItem.status == "failed",
        )
        .values(
            status="queued",
            clear_status_code=None,
            warm_status_code=None,
            detail=None,
            elapsed_ms=None,
            updated_at=now,
        )
    )
    run.failed = max(0, run.failed - len(failed_ids))
    run.status = "running"
    run.finished_at = None
    await db.commit()
    return list(failed_ids)


# ----- watchdog recovery -----


async def fail_orphaned_items(
    db: AsyncSession, run_id: int, cutoff: datetime
) -> int:
    """Fail items stuck in 'running' since before ``cutoff`` (their worker died
    mid-request) and bump the run for each. Returns how many were recovered."""
    stale = (
        (
            await db.execute(
                select(DomainCacheRunItem.id).where(
                    DomainCacheRunItem.run_id == run_id,
                    DomainCacheRunItem.status == "running",
                    DomainCacheRunItem.updated_at < cutoff,
                )
            )
        )
        .scalars()
        .all()
    )
    recovered = 0
    now = datetime.now(timezone.utc)
    for iid in stale:
        res = await db.execute(
            update(DomainCacheRunItem)
            .where(
                DomainCacheRunItem.id == iid,
                DomainCacheRunItem.status == "running",
            )
            .values(
                status="failed",
                detail=(
                    "Worker stopped before this domain finished (recovered by "
                    "the watchdog). Use Retry failed to retry."
                ),
                updated_at=now,
            )
        )
        await db.commit()
        if (res.rowcount or 0) == 1:
            await _bump(db, run_id=run_id, field="failed")
            recovered += 1
    return recovered


async def has_in_flight_items(db: AsyncSession, run_id: int) -> bool:
    """True if any item is currently 'running' for this run."""
    row = (
        await db.execute(
            select(DomainCacheRunItem.id)
            .where(
                DomainCacheRunItem.run_id == run_id,
                DomainCacheRunItem.status == "running",
            )
            .limit(1)
        )
    ).first()
    return row is not None
