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
    if domain is None or domain.deleted_at is not None:
        # Trashed domains are not pickable as publish targets.
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

    return _to_detail(job, domain.name, domain)


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
    job = await db.get(PublishJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Not found")
    # Fetch the full domain (not just its name) so we can reconstruct the
    # exact outgoing request as a copy-pasteable curl for debugging.
    domain = await db.get(Domain, job.domain_id) if job.domain_id else None
    return _to_detail(job, domain.name if domain else None, domain)


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


def _extract_sent_slug(payload: object) -> str | None:
    """The slug from the outgoing body. Posted/failed jobs store the real body
    under ``slug``; a queued single job stashes the pre-normalization fields
    under the ``__fields`` sentinel. None when no slug was present."""
    if not isinstance(payload, dict):
        return None
    v = payload.get("slug")
    if isinstance(v, str):
        return v
    fields = payload.get("__fields")
    if isinstance(fields, dict) and isinstance(fields.get("slug"), str):
        return fields["slug"]
    return None


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
        # Migration 0026: upstream HTTP code. NULL for rows that predate
        # the migration; the UI treats null as "unknown" and falls back to
        # inferring from status / error text.
        status_code=job.status_code,
        error=job.error,
        warnings=list(job.warnings) if job.warnings else None,
        profile_name=job.profile_name,
        created_by_id=job.created_by_id,
        slug=_extract_sent_slug(job.payload_sent),
    )


def _to_detail(
    job: PublishJob, domain_name: str | None, domain: Domain | None = None
) -> PublishJobDetail:
    base = _to_read(job, domain_name)
    return PublishJobDetail(
        **base.model_dump(),
        payload_sent=job.payload_sent,
        response_json=job.response_json,
        curl_preview=_build_curl_preview(job, domain),
    )


def _shell_single_quote(s: str) -> str:
    """Wrap a value in single quotes for a shell command, escaping any
    embedded single quotes the POSIX way (`'` → `'\\''`)."""
    return "'" + s.replace("'", "'\\''") + "'"


def _masked_auth_header(domain: Domain) -> tuple[str, str] | None:
    """The auth header that WOULD be sent, with the secret masked. We never
    read the stored credentials, so nothing sensitive can leak."""
    at = (domain.auth_type or "").strip()
    if at == "bearer":
        return ("Authorization", "Bearer <REDACTED>")
    if at == "basic_auth":
        return ("Authorization", "Basic <REDACTED>")
    if at == "api_key_header":
        # The header NAME lives in the (encrypted) credentials JSON alongside
        # the secret value; we don't decrypt it here, so show a placeholder.
        return ("<api-key-header>", "<REDACTED>")
    return None


def _build_curl_preview(job: PublishJob, domain: Domain | None) -> str | None:
    """Reconstruct the exact outgoing request for this row as a copy-pasteable
    curl — method, URL, headers (auth masked) and the real JSON body that was
    sent. Returns None when there's nothing meaningful to show yet."""
    import json

    body = job.payload_sent
    # Queued single jobs stash the to-publish fields under a `__fields`
    # sentinel before the worker overwrites payload_sent with the real body —
    # nothing has hit the wire yet, so no curl.
    if not isinstance(body, dict) or "__fields" in body or domain is None:
        return None

    base = (domain.base_url or "").rstrip("/")
    headers: list[tuple[str, str]] = [("Content-Type", "application/json")]
    auth = _masked_auth_header(domain)

    if domain.cms_type == "custom":
        endpoint_path = (domain.custom_config or {}).get("endpoint_path") or ""
        url = f"{base}{endpoint_path}"
        prefix = ""
    else:
        # WordPress writes via the REST API after a lookup; we don't store the
        # resolved post type / id, so this is a best-effort approximation.
        url = f"{base}/wp-json/wp/v2/posts"
        prefix = (
            "# NOTE: approximate — WordPress first looks up the post, then "
            "POSTs to /wp-json/wp/v2/<post_type>[/<id>].\n"
        )

    if auth is not None:
        headers.append(auth)

    body_json = json.dumps(body, ensure_ascii=False)
    lines = [f"curl -X POST {_shell_single_quote(url)}"]
    for k, v in headers:
        lines.append(f"  -H {_shell_single_quote(f'{k}: {v}')}")
    lines.append(f"  -d {_shell_single_quote(body_json)}")
    return prefix + " \\\n".join(lines)
