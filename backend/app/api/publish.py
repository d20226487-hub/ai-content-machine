"""Single-mode publish endpoint + publish job history.

Access: admin or manager (same as Domains).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.models import Domain, PublishJob, User
from app.db.session import get_db
from app.schemas.publish import (
    PublishDefaults,
    PublishJobDetail,
    PublishJobListResponse,
    PublishJobRead,
    PublishSingleRequest,
)
from app.services.publish_rate_limit import (
    DomainRateLimits,
    load_global_defaults,
    update_global_defaults,
)
from app.tasks.publish_single import publish_one_single

router = APIRouter(
    prefix="/publish",
    tags=["publish"],
    dependencies=[Depends(require_role("admin", "manager"))],
)


@router.get("/defaults", response_model=PublishDefaults)
async def get_publish_defaults(
    db: AsyncSession = Depends(get_db),
) -> PublishDefaults:
    g = await load_global_defaults(db)
    return PublishDefaults(**g.__dict__)


@router.put("/defaults", response_model=PublishDefaults)
async def set_publish_defaults(
    payload: PublishDefaults,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin")),
) -> PublishDefaults:
    saved = await update_global_defaults(
        db,
        DomainRateLimits(**payload.model_dump()),
        updated_by_id=actor.id,
    )
    return PublishDefaults(**saved.__dict__)


@router.post("/single", response_model=PublishJobDetail, status_code=status.HTTP_202_ACCEPTED)
async def publish_single(
    payload: PublishSingleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> PublishJobDetail:
    """Queue a single-publish job and return immediately.

    The actual HTTP call to WordPress / Custom CMS happens in a Celery worker
    (``app.tasks.publish_single.publish_one_single``). The client polls
    ``GET /publish/jobs/{id}`` to see when it lands. Why queue: the publish
    can hang up to ~330 s under retry/backoff; running it in the request
    handler made user-retries (refresh, double-submit) duplicate posts.
    """
    domain = await db.get(Domain, payload.domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Validate required fields up front (per the chosen profile when WP).
    # For Custom CMS the placeholders in body_template imply the required
    # fields; we accept whatever the caller sends.
    if domain.cms_type == "wordpress":
        cfg = domain.publish_config or {}
        # New shape: profiles[]. Legacy shape: top-level {post_type, fields}.
        profiles = cfg.get("profiles") if isinstance(cfg, dict) else None
        if isinstance(profiles, list) and profiles:
            chosen = None
            if payload.profile_name:
                chosen = next(
                    (p for p in profiles if isinstance(p, dict) and p.get("name") == payload.profile_name),
                    None,
                )
            if chosen is None:
                chosen = next((p for p in profiles if isinstance(p, dict)), None)
            field_defs = (chosen or {}).get("fields", []) if chosen else []
        else:
            field_defs = cfg.get("fields", []) if isinstance(cfg, dict) else []

        for f in field_defs:
            if not f.get("required"):
                continue
            v = payload.fields.get(f["key"])
            if v is None or v == "":
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required field: {f.get('label') or f['key']}",
                )

    # Stash the to-publish fields in a sentinel slot under payload_sent so the
    # worker can read them. payload_sent is overwritten with the actual
    # outgoing CMS body once the publish runs, so the sentinel is short-lived.
    job = PublishJob(
        domain_id=domain.id,
        source_kind="single",
        source_ref=payload.source_ref,
        status="queued",
        language=payload.language,
        profile_name=payload.profile_name,
        created_by_id=actor.id,
        payload_sent={"__fields": payload.fields},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue AFTER the commit — otherwise a worker can pick the row up before
    # the row is visible.
    publish_one_single.delay(job.id)

    return _to_detail(job, domain.name)


@router.get("/jobs", response_model=PublishJobListResponse)
async def list_publish_jobs(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    source_kind: str | None = Query(
        None,
        description="Filter to a specific source_kind ('single' | 'bulk_row' | 'bulk_cell').",
    ),
    domain_id: int | None = None,
    generation_id: int | None = Query(
        None,
        description="Filter to jobs whose source_ref->>'generation_id' matches this id.",
    ),
    run_id: int | None = Query(
        None,
        description="Filter to jobs whose source_ref->>'run_id' matches this id (bulk runs).",
    ),
) -> PublishJobListResponse:
    base = select(PublishJob, Domain.name).join(
        Domain, Domain.id == PublishJob.domain_id, isouter=True
    )
    count_stmt = select(func.count(PublishJob.id))

    conditions = []
    if status_filter:
        conditions.append(PublishJob.status == status_filter)
    if source_kind:
        conditions.append(PublishJob.source_kind == source_kind)
    if domain_id is not None:
        conditions.append(PublishJob.domain_id == domain_id)
    if generation_id is not None:
        conditions.append(
            PublishJob.source_ref["generation_id"].astext == str(generation_id)
        )
    if run_id is not None:
        conditions.append(
            PublishJob.source_ref["run_id"].astext == str(run_id)
        )
    for c in conditions:
        base = base.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()
    base = (
        base.order_by(PublishJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(base)).all()
    items = [_to_read(j, dn) for (j, dn) in rows]
    return PublishJobListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/jobs/{job_id}", response_model=PublishJobDetail)
async def get_publish_job(
    job_id: int, db: AsyncSession = Depends(get_db)
) -> PublishJobDetail:
    row = (
        await db.execute(
            select(PublishJob, Domain.name)
            .join(Domain, Domain.id == PublishJob.domain_id, isouter=True)
            .where(PublishJob.id == job_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    job, domain_name = row
    return _to_detail(job, domain_name)


_TERMINAL_JOB_STATUSES = ("posted", "failed")


@router.delete(
    "/jobs/completed",
    status_code=status.HTTP_200_OK,
)
async def clear_completed_publish_jobs(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
    source_kind: str | None = Query(
        None,
        description="Restrict the wipe to one source_kind. Omit to clear every kind.",
    ),
) -> dict:
    """Delete every publish_job in a terminal state (posted | failed).

    In-flight rows (queued / posting) are left alone — cancel them first if
    you want them gone. Pass ``source_kind=single`` from the Single Runs page
    so the wipe doesn't also clear bulk-row history (which is owned by its
    parent BulkPublishRun).
    """
    stmt = sa_delete(PublishJob).where(PublishJob.status.in_(_TERMINAL_JOB_STATUSES))
    if source_kind:
        stmt = stmt.where(PublishJob.source_kind == source_kind)
    result = await db.execute(stmt)
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_publish_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_role("admin", "manager")),
) -> Response:
    job = await db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Not found")
    if job.status not in _TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete a publish job in status {job.status!r}. Wait for it to finish first.",
        )
    await db.delete(job)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _to_read(job: PublishJob, domain_name: str | None) -> PublishJobRead:
    return PublishJobRead(
        id=job.id,
        created_at=job.created_at,
        finished_at=job.finished_at,
        domain_id=job.domain_id,
        domain_name=domain_name,
        source_kind=job.source_kind,  # type: ignore[arg-type]
        source_ref=job.source_ref,
        status=job.status,  # type: ignore[arg-type]
        language=job.language,
        cms_post_id=job.cms_post_id,
        cms_post_url=job.cms_post_url,
        error=job.error,
        warnings=list(job.warnings) if job.warnings else None,
        profile_name=job.profile_name,
        created_by_id=job.created_by_id,
    )


def _to_detail(job: PublishJob, domain_name: str | None) -> PublishJobDetail:
    base = _to_read(job, domain_name)
    return PublishJobDetail(
        **base.model_dump(),
        payload_sent=job.payload_sent,
        response_json=job.response_json,
    )
