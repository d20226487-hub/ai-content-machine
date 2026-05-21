"""Multi-domain language-sync endpoint.

Single endpoint at ``POST /publish/languages/sync``. Lives in its own
file (rather than in the existing publish router) because the use case is
distinct from publishing — it's a pre-flight site-management action that
can also be invoked outside any bulk-publish flow.

Access: admin or manager (same as the rest of /publish — anyone who can
publish to a domain should also be able to push languages to it).
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_role
from app.db.models import Domain, LanguageSyncResult as LanguageSyncResultRow
from app.db.models import LanguageSyncRun as LanguageSyncRunRow
from app.db.models import User
from app.db.session import get_db
from app.schemas.language_sync import (
    LanguageSyncOneResult,
    LanguageSyncRequest,
    LanguageSyncResolveKnownDomain,
    LanguageSyncResolveRequest,
    LanguageSyncResolveResult,
    LanguageSyncResult,
    LanguageSyncResultRead,
    LanguageSyncRunDetail,
    LanguageSyncRunListResponse,
    LanguageSyncRunRead,
)
from app.services.language_sync import sync_one_domain

router = APIRouter(
    prefix="/publish/languages",
    tags=["publish", "languages"],
    dependencies=[Depends(require_role("admin", "manager"))],
)

# Cap concurrent outbound HTTP. Per-domain rate limiting (like the
# publish-bulk path) would be overkill for a one-shot sync — but we still
# want to avoid hammering 50 sites at once if a user submits a 50-row
# table. 5 in-flight at a time is enough to keep total wall-clock low.
_CONCURRENCY = 5


@router.post("/sync", response_model=LanguageSyncResult)
async def sync_languages(
    payload: LanguageSyncRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> LanguageSyncResult:
    """Push a language set to each target site in parallel.

    Resolution: target names are matched against ``Domain.name``
    exactly. Unknown names come back as ``skipped`` so the UI can show
    "the table references 'shop-zz' but no such domain exists".
    Soft-deleted domains are excluded from the lookup.
    """
    # Dedup names so a table with the same domain on 50 rows produces
    # exactly one POST. Preserve order for stable result rendering.
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

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _run(target) -> tuple[LanguageSyncOneResult, list[str]]:
        domain = by_name.get(target.domain_name)
        # Normalize the language list the same way the service does, so
        # what we persist matches what was actually sent (lowercase, deduped,
        # no whitespace-only entries).
        norm = sorted({s.strip().lower() for s in target.languages if s and s.strip()})
        if domain is None:
            return (
                LanguageSyncOneResult(
                    domain_name=target.domain_name,
                    ok=False,
                    skipped=True,
                    skip_reason="No domain with this name (check /publish/domains)",
                ),
                norm,
            )
        async with sem:
            return await sync_one_domain(domain, target.languages), norm

    paired = await asyncio.gather(*[_run(t) for t in ordered_targets])
    results = [p[0] for p in paired]

    # Persist the run so it shows up in the history page. Counts are
    # tallied here instead of via SQL aggregation later so the listing
    # never has to GROUP BY across the results table.
    ok_count = sum(1 for r in results if r.ok)
    skip_count = sum(1 for r in results if r.skipped)
    fail_count = sum(1 for r in results if not r.ok and not r.skipped)

    run = LanguageSyncRunRow(
        created_by_id=actor.id,
        source=payload.source,
        total_count=len(results),
        ok_count=ok_count,
        fail_count=fail_count,
        skip_count=skip_count,
    )
    db.add(run)
    await db.flush()  # populate run.id before child inserts

    for (result, langs) in paired:
        db.add(
            LanguageSyncResultRow(
                run_id=run.id,
                domain_id=result.domain_id,
                domain_name=result.domain_name,
                languages=langs,
                ok=result.ok,
                skipped=result.skipped,
                skip_reason=result.skip_reason,
                status_code=result.status_code,
                detail=result.detail,
                elapsed_ms=result.elapsed_ms,
            )
        )
    await db.commit()

    return LanguageSyncResult(run_id=run.id, results=results)


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
