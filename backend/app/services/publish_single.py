"""Async core for processing a single (non-bulk) publish job.

The Celery task in ``app/tasks/publish_single.py`` wraps this. The API endpoint
``POST /publish/single`` no longer runs the publish synchronously — it inserts
a ``PublishJob`` row in ``status='queued'`` and enqueues the task. Clients poll
``GET /publish/jobs/{id}`` for the terminal state.

Why move it off the request handler:
  * The publish call could hang up to ~330 s under retry/backoff. A user
    hitting Refresh would re-trigger the whole flow, producing duplicate
    posts. Queuing means a retry is idempotent (the same job_id is what
    gets watched for completion).
  * The web worker process can free up to serve other requests instead of
    blocking on a slow upstream WP/Custom API.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.registry import UnsupportedCms, get_cms_client
from app.db.models import Domain, PublishJob
from app.services.error_log import log_error
from app.services.media_cache import MediaCache
from app.services.publish_rate_limit import domain_rate_key, resolve_for_domain
from app.services.rate_limit import get_rate_limiter


async def process_single_job(db: AsyncSession, *, job_id: int) -> None:
    """Resolve and complete a queued single-publish job.

    Idempotent: if the job has already reached a terminal state ('posted' /
    'failed') we skip. Celery acks_late=True can otherwise redeliver the same
    task and we'd post twice.
    """
    job = await db.get(PublishJob, job_id)
    if job is None:
        return
    if job.status in ("posted", "failed"):
        return
    if job.status == "posting":
        # Already in flight on another worker. Don't double-fire.
        return
    if job.source_kind != "single":
        return
    if job.domain_id is None:
        job.status = "failed"
        job.error = "Domain has been deleted; cannot publish."
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return

    domain = await db.get(Domain, job.domain_id)
    if domain is None:
        job.status = "failed"
        job.error = "Domain has been deleted; cannot publish."
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return
    if domain.deleted_at is not None:
        # Race: the job was queued while the domain was active, then
        # the domain got trashed before the worker picked us up.
        # Surface a clear message so the user knows where to look.
        job.status = "failed"
        job.error = (
            f"Domain {domain.name!r} was moved to Trash before this "
            "job ran. Restore the domain from /publish/domains/trash "
            "and retry."
        )
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return

    # Flip queued → posting so a duplicate redelivery sees it and short-circuits.
    job.status = "posting"
    await db.commit()

    fields = (job.payload_sent or {}).get("__fields", {})
    # The API stores fields under a sentinel key; this avoids polluting
    # payload_sent which otherwise gets overwritten with the actual outgoing
    # body. See `enqueue_single_publish` below.
    language = job.language
    profile_name = job.profile_name

    try:
        media_cache = MediaCache(db, domain.id) if domain.cms_type == "wordpress" else None
        client = get_cms_client(domain, media_cache=media_cache)
    except UnsupportedCms as e:
        job.status = "failed"
        job.error = str(e)
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return

    limits = await resolve_for_domain(db, domain)
    limiter = get_rate_limiter()

    try:
        async with limiter.acquire(
            provider_code=domain_rate_key(domain.id),
            max_concurrency=limits.max_concurrency,
            requests_per_minute=limits.requests_per_minute,
            inter_request_delay_ms=limits.inter_request_delay_ms,
        ):
            result = await client.publish_post(
                fields=fields,
                language=language,
                profile_name=profile_name or None,
            )
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = f"{type(e).__name__}: {e}"
        job.payload_sent = None
        job.response_json = None
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await log_error(
            db,
            source="worker",
            category="publish_error",
            message=job.error,
            user_id=job.created_by_id,
            provider=None,
            context={
                "endpoint": "publish_single_task",
                "publish_job_id": job.id,
                "domain_id": domain.id,
                "domain_name": domain.name,
            },
            resource_type="publish_job",
            resource_id=job.id,
        )
        return

    job.payload_sent = result.payload_sent
    job.response_json = result.response_json
    job.cms_post_id = result.cms_post_id
    job.cms_post_url = result.cms_post_url
    job.warnings = list(result.warnings) if result.warnings else None
    job.finished_at = datetime.now(timezone.utc)

    if result.ok:
        job.status = "posted"
        await db.commit()
    else:
        job.status = "failed"
        job.error = result.error
        await db.commit()
        await log_error(
            db,
            source="worker",
            category="publish_error",
            message=result.error or "publish failed",
            user_id=job.created_by_id,
            provider=None,
            status_code=result.status_code,
            context={
                "endpoint": "publish_single_task",
                "publish_job_id": job.id,
                "domain_id": domain.id,
                "domain_name": domain.name,
                "cms_type": domain.cms_type,
                "language": language,
            },
            resource_type="publish_job",
            resource_id=job.id,
        )
