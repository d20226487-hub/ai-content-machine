"""Multi-domain language-sync endpoint.

Single endpoint at ``POST /publish/languages/sync``. Lives in its own
file (rather than in the existing publish router) because the use case is
distinct from publishing — it's a pre-flight site-management action that
can also be invoked outside any bulk-publish flow.

Access: admin or manager (same as the rest of /publish — anyone who can
publish to a domain should also be able to push languages to it).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_role
from app.db.models import Domain, LanguageSyncResult as LanguageSyncResultRow
from app.db.models import LanguageSyncRun as LanguageSyncRunRow
from app.db.models import User
from app.db.session import get_db
from app.schemas.language_sync import (
    LanguageSyncRequest,
    LanguageSyncResolveKnownDomain,
    LanguageSyncResolveRequest,
    LanguageSyncResolveResult,
    LanguageSyncResultRead,
    LanguageSyncRunDetail,
    LanguageSyncRunListResponse,
    LanguageSyncRunRead,
    LanguageSyncTrigger,
)
from app.tasks.language_sync import resume_langsync, run_langsync

router = APIRouter(
    prefix="/publish/languages",
    tags=["publish", "languages"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


async def _creator_name(db: AsyncSession, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    return (
        await db.execute(select(User.full_name).where(User.id == user_id))
    ).scalar_one_or_none()


def _run_summary(run: LanguageSyncRunRow, creator: str | None) -> LanguageSyncRunRead:
    return LanguageSyncRunRead(
        id=run.id,
        created_at=run.created_at,
        created_by_id=run.created_by_id,
        created_by_name=creator,
        source=run.source,
        status=run.status,
        total_count=run.total_count,
        ok_count=run.ok_count,
        fail_count=run.fail_count,
        skip_count=run.skip_count,
    )


@router.post(
    "/sync",
    response_model=LanguageSyncTrigger,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_languages(
    payload: LanguageSyncRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LanguageSyncTrigger:
    """Enqueue a background sync that pushes a language set to each target
    site. Returns immediately with the new ``run_id`` (202) — the work runs
    in a Celery task that updates progress + per-site outcomes as it goes, so
    the UI polls the run detail (or navigates to its page) rather than
    blocking on the whole fan-out.

    Resolution: target names are matched against ``Domain.name`` exactly.
    Unknown names are stored with ``domain_id=NULL`` and the worker records
    them as ``skipped`` ("no such domain"). Soft-deleted domains are excluded.
    """
    # Dedup names so a table with the same domain on 50 rows produces exactly
    # one target. Preserve order for stable result rendering.
    seen: set[str] = set()
    ordered_targets = []
    for t in payload.targets:
        if t.domain_name in seen:
            continue
        seen.add(t.domain_name)
        ordered_targets.append(t)

    # One batched lookup — avoids N round trips on a 50-site table.
    rows = (
        await db.execute(
            select(Domain).where(
                Domain.name.in_([t.domain_name for t in ordered_targets]),
                Domain.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_name = {d.name: d for d in rows}

    run = LanguageSyncRunRow(
        created_by_id=actor.id,
        source=payload.source,
        status="queued",
        total_count=len(ordered_targets),
        ok_count=0,
        fail_count=0,
        skip_count=0,
    )
    db.add(run)
    await db.flush()  # populate run.id before child inserts

    for t in ordered_targets:
        domain = by_name.get(t.domain_name)
        # Normalize once at seed time — what we persist as the attempted set
        # matches what the worker will send (lowercase, deduped, trimmed).
        norm = sorted({s.strip().lower() for s in t.languages if s and s.strip()})
        db.add(
            LanguageSyncResultRow(
                run_id=run.id,
                domain_id=domain.id if domain else None,
                domain_name=t.domain_name,
                languages=norm,
                state="pending",
                ok=False,
                skipped=False,
            )
        )
    await db.commit()

    run_langsync.delay(run.id)
    return LanguageSyncTrigger(run_id=run.id, status=run.status)


@router.post("/runs/{run_id}/retry-failed", response_model=LanguageSyncRunRead)
async def retry_failed(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LanguageSyncRunRead:
    """Re-attempt the failed targets of a finished run, IN PLACE. Failed
    result rows (attempted, not ok, not skipped) flip back to ``pending`` and
    the run re-queues; previously-ok and skipped rows are left untouched. 400
    if the run is still active or has nothing to retry."""
    run = await db.get(LanguageSyncRunRow, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "done":
        raise HTTPException(status_code=400, detail="Run is still active")

    failed = (
        await db.execute(
            select(LanguageSyncResultRow).where(
                LanguageSyncResultRow.run_id == run_id,
                LanguageSyncResultRow.state == "done",
                LanguageSyncResultRow.ok.is_(False),
                LanguageSyncResultRow.skipped.is_(False),
            )
        )
    ).scalars().all()
    if not failed:
        raise HTTPException(status_code=400, detail="No failed targets to retry")

    for r in failed:
        r.state = "pending"
        r.ok = False
        r.skip_reason = None
        r.status_code = None
        r.detail = None
        r.elapsed_ms = None
    run.status = "queued"
    run.finished_at = None
    run.fail_count = 0
    await db.commit()

    resume_langsync.delay(run.id)
    return _run_summary(run, await _creator_name(db, run.created_by_id))


@router.post("/runs/{run_id}/resume", response_model=LanguageSyncRunRead)
async def resume_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LanguageSyncRunRead:
    """Re-enqueue an active run whose worker died mid-flight (so it sits at
    'running' with pending targets left). Idempotent — the task re-queries
    pending, so a double-resume can't double-send. 400 on a finished run
    (use retry-failed for those)."""
    run = await db.get(LanguageSyncRunRow, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status == "done":
        raise HTTPException(
            status_code=400, detail="Run already finished — use Retry failed"
        )
    resume_langsync.delay(run.id)
    return _run_summary(run, await _creator_name(db, run.created_by_id))


# ---------- run history ----------


@router.get("/runs", response_model=LanguageSyncRunListResponse)
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> LanguageSyncRunListResponse:
    """Paginated history of past sync batches, newest first.

    `created_by_name` is denormalized into the response by a join — keeps
    the frontend simpler (no per-row user lookup) and the cost is one
    LEFT JOIN per page (max 100 rows).
    """
    offset = (page - 1) * page_size
    total = int(
        (await db.execute(select(func.count(LanguageSyncRunRow.id)))).scalar() or 0
    )
    # LEFT JOIN to users so a deleted creator shows up as "—" rather
    # than dropping the run from the listing.
    rows = (
        await db.execute(
            select(LanguageSyncRunRow, User.full_name)
            .outerjoin(User, User.id == LanguageSyncRunRow.created_by_id)
            .order_by(LanguageSyncRunRow.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()
    items = [
        LanguageSyncRunRead(
            id=run.id,
            created_at=run.created_at,
            created_by_id=run.created_by_id,
            created_by_name=name,
            source=run.source,
            status=run.status,
            total_count=run.total_count,
            ok_count=run.ok_count,
            fail_count=run.fail_count,
            skip_count=run.skip_count,
        )
        for run, name in rows
    ]
    return LanguageSyncRunListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/runs/{run_id}", response_model=LanguageSyncRunDetail)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> LanguageSyncRunDetail:
    """One run with its full result list. Results aren't paginated within
    a run — even a 200-domain batch fits comfortably in a single page."""
    run = (
        await db.execute(
            select(LanguageSyncRunRow)
            .options(selectinload(LanguageSyncRunRow.results))
            .where(LanguageSyncRunRow.id == run_id)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    creator = None
    if run.created_by_id is not None:
        creator = (
            await db.execute(select(User.full_name).where(User.id == run.created_by_id))
        ).scalar_one_or_none()

    return LanguageSyncRunDetail(
        id=run.id,
        created_at=run.created_at,
        created_by_id=run.created_by_id,
        created_by_name=creator,
        source=run.source,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        total_count=run.total_count,
        ok_count=run.ok_count,
        fail_count=run.fail_count,
        skip_count=run.skip_count,
        results=[
            LanguageSyncResultRead.model_validate(r)
            for r in sorted(run.results, key=lambda r: r.id)
        ],
    )


# ---------- CSV import: name resolution ----------


@router.post("/resolve", response_model=LanguageSyncResolveResult)
async def resolve_names(
    payload: LanguageSyncResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> LanguageSyncResolveResult:
    """Pre-import name check used by the CSV import modal.

    Caller posts a list of domain names (parsed from the CSV's `domain`
    column); we look them up against ``Domain.name`` and return which
    ones exist and which don't. The frontend uses this to hard-fail the
    import — if any name is unknown the user has to fix the CSV before
    we'll commit anything. Stops fat-finger typos from quietly skipping
    rows during a 100-site batch.

    Dedup happens here so duplicate rows in the CSV don't inflate the
    request shape.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for n in payload.names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)

    rows = (
        await db.execute(
            select(Domain).where(
                Domain.name.in_(ordered),
                Domain.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_name = {d.name: d for d in rows}
    known: list[LanguageSyncResolveKnownDomain] = []
    unknown: list[str] = []
    for n in ordered:
        d = by_name.get(n)
        if d is None:
            unknown.append(n)
            continue
        known.append(
            LanguageSyncResolveKnownDomain(
                id=d.id,
                name=d.name,
                has_credentials=bool(d.credentials_encrypted),
                cms_type=d.cms_type,
            )
        )
    return LanguageSyncResolveResult(known=known, unknown=unknown)
