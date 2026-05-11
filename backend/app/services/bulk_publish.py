"""Async core of the bulk-publish per-row task.

Run lifecycle (the seed task triggers, child tasks run, the run is done when
``done + failed + skipped == total`` and status is still ``running``).

Status semantics:
  queued      seed task hasn't started enqueueing yet
  running     children processing
  paused      children no-op when they see this; resume re-enqueues
  cancelled   children no-op; terminal
  done        all candidate rows accounted for
  failed      seed task crashed before children could run

Mode semantics:
  single   every row in the run goes to the same (domain, profile_name)
  multi    each row's target is resolved from cells in the columns
           referenced by run.domain_column_id / run.profile_column_id
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.registry import UnsupportedCms, get_cms_client
from app.db.models import (
    BulkPublishRun,
    BulkTableCell,
    BulkTableRow,
    Domain,
    PublishJob,
)
from app.services.error_log import log_error
from app.services.media_cache import MediaCache
from app.services.publish_rate_limit import domain_rate_key, resolve_for_domain
from app.services.rate_limit import get_rate_limiter


# ---------- per-row target resolution ----------


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    domain: Domain
    profile_name: str  # '' for Custom CMS or "use default" in WP


@dataclass(frozen=True, slots=True)
class ResolveError:
    message: str  # surfaced to the publish_jobs.error column
    domain_id: int | None = None  # set if we resolved domain but failed later


async def resolve_row_target(
    db: AsyncSession, *, run: BulkPublishRun, row_id: int
) -> ResolvedTarget | ResolveError:
    """Decide where this row should publish.

    Single mode: returns the run-level (domain, profile_name).
    Multi mode: reads cells from run.domain_column_id / .profile_column_id,
    looks up domain by name, validates it isn't Custom-CMS (not supported
    in multi mode v1).
    """
    if run.mode == "single":
        if run.domain_id is None:
            return ResolveError(message="Domain has been deleted; cannot publish.")
        domain = await db.get(Domain, run.domain_id)
        if domain is None:
            return ResolveError(message="Domain has been deleted; cannot publish.")
        return ResolvedTarget(domain=domain, profile_name=run.profile_name or "")

    # ---- multi ----
    if run.domain_column_id is None:
        return ResolveError(
            message="Multi-mode run is missing domain_column_id (column may have been deleted)."
        )

    domain_value = await _read_cell_value(
        db, row_id=row_id, column_id=run.domain_column_id
    )
    if not domain_value:
        return ResolveError(message="Domain column is empty for this row.")

    # Lookup by exact name. The migration enforces uniqueness so at most one row.
    domain = (
        await db.execute(select(Domain).where(Domain.name == domain_value))
    ).scalar_one_or_none()
    if domain is None:
        return ResolveError(message=f"Domain not found: {domain_value!r}.")

    if domain.cms_type != "wordpress":
        return ResolveError(
            message=(
                f"Multi-site publish to Custom CMS is not supported in this "
                f"version. Use Single mode for {domain.name}."
            ),
            domain_id=domain.id,
        )

    profile_name = ""
    if run.profile_column_id is not None:
        profile_value = await _read_cell_value(
            db, row_id=row_id, column_id=run.profile_column_id
        )
        if not profile_value:
            return ResolveError(
                message="Profile column is empty for this row.",
                domain_id=domain.id,
            )

        profiles = (domain.publish_config or {}).get("profiles") or []
        names = [p.get("name") for p in profiles if isinstance(p, dict)]
        if profile_value not in names:
            available = ", ".join(repr(n) for n in names) or "(none configured)"
            return ResolveError(
                message=(
                    f"Profile {profile_value!r} not found for domain "
                    f"{domain.name!r}. Available: {available}."
                ),
                domain_id=domain.id,
            )
        profile_name = profile_value

    return ResolvedTarget(domain=domain, profile_name=profile_name)


async def _read_cell_value(
    db: AsyncSession, *, row_id: int, column_id: int
) -> str:
    cell = (
        await db.execute(
            select(BulkTableCell.value).where(
                BulkTableCell.row_id == row_id,
                BulkTableCell.column_id == column_id,
            )
        )
    ).scalar_one_or_none()
    return (cell or "").strip()


async def has_active_publish_job(
    db: AsyncSession, *, run_id: int, row_id: int
) -> bool:
    """Return True iff a non-failed PublishJob exists for (run_id, row_id).

    Used by ``publish_one_row`` to short-circuit Celery redeliveries: with
    ``task_acks_late=True``, a worker crash between writing status='posting'
    and ``_bump_counter`` causes Celery to redeliver the same task, which
    without this guard would re-post the row to WordPress. Failed jobs are
    NOT counted so that Celery retries (the ``failed`` path) can still
    re-attempt — only ``posted`` (terminal-success) and ``posting``
    (in-flight) lock out a duplicate run.
    """
    existing = (
        await db.execute(
            select(PublishJob).where(
                PublishJob.source_kind == "bulk_row",
                PublishJob.source_ref["run_id"].astext == str(run_id),
                PublishJob.source_ref["row_id"].astext == str(row_id),
                PublishJob.status.in_(("posted", "posting")),
            )
        )
    ).scalars().first()
    return existing is not None


async def candidate_row_ids(
    db: AsyncSession, run: BulkPublishRun
) -> list[int]:
    """Compute candidate rows from row_filter + cell_filter.

    Excludes rows that already have a finalized (posted/failed) PublishJob
    for this run so resume re-enqueues only the leftover work.
    """
    base = (
        select(BulkTableRow.id)
        .where(BulkTableRow.table_id == run.table_id)
        .order_by(BulkTableRow.position)
    )
    if run.row_filter == "selected":
        ids = (run.selection or {}).get("row_ids") or []
        if not ids:
            return []
        base = base.where(BulkTableRow.id.in_([int(x) for x in ids]))
    elif run.row_filter == "range":
        # Range is 1-based in the UI (visible row numbers); position is 0-based.
        start = int((run.selection or {}).get("start") or 1)
        end = int((run.selection or {}).get("end") or 0)
        base = base.where(
            BulkTableRow.position >= start - 1, BulkTableRow.position <= end - 1
        )
    # 'all' → no row constraint

    row_ids = (await db.execute(base)).scalars().all()
    if not row_ids:
        return []

    # Cell filter: inspect the back-fill target column for "already published" /
    # "previously failed" detection.
    if run.cell_filter == "all":
        candidates = list(row_ids)
    else:
        post_id_col = (run.back_fill or {}).get("post_id_target")
        if post_id_col is None:
            # No way to detect — fall back to processing everything.
            candidates = list(row_ids)
        else:
            cells = (
                await db.execute(
                    select(BulkTableCell.row_id, BulkTableCell.value).where(
                        BulkTableCell.row_id.in_(row_ids),
                        BulkTableCell.column_id == int(post_id_col),
                    )
                )
            ).all()
            value_by_row = {r: (v or "") for r, v in cells}
            if run.cell_filter == "unpublished":
                candidates = [r for r in row_ids if not value_by_row.get(r)]
            elif run.cell_filter == "failed":
                # "Failed" without a post_id is the only signal we have; same
                # as unpublished for now. Phase 4 may add a richer status col.
                candidates = [r for r in row_ids if not value_by_row.get(r)]
            else:
                candidates = list(row_ids)

    if not candidates:
        return []

    # Skip rows already processed OR currently in flight for this run.
    # Including 'posting' is what makes resume idempotent — without it, a Pause
    # taken mid-flight leaves rows whose child task was running but had already
    # committed status='posting'. The seed re-enqueueing on Resume would then
    # double-publish those rows (we saw exactly this on run #7: 7 in-flight
    # rows became 7 duplicates → counters overshot total).
    processed = (
        await db.execute(
            select(PublishJob.source_ref).where(
                PublishJob.source_kind == "bulk_row",
                PublishJob.status.in_(("posted", "failed", "posting")),
                PublishJob.source_ref["run_id"].astext == str(run.id),
            )
        )
    ).all()
    done_row_ids: set[int] = set()
    for (sref,) in processed:
        try:
            done_row_ids.add(int((sref or {}).get("row_id")))
        except (TypeError, ValueError):
            continue

    return [r for r in candidates if r not in done_row_ids]


async def publish_one_row(
    db: AsyncSession, *, run_id: int, row_id: int
) -> str:
    """Run a single bulk-publish attempt for one row.

    Returns one of: 'posted' | 'failed' | 'skipped'.
    """
    run = await db.get(BulkPublishRun, run_id)
    if run is None:
        return "skipped"
    if run.status in ("paused", "cancelled"):
        # Pause/cancel: no work, no counter change. (Resume re-enqueues.)
        return "skipped"

    # Idempotency guard against Celery redelivery (task_acks_late=True). If the
    # worker dies between writing status='posting' and the counter bump,
    # Celery requeues the same task — without this guard the row would be
    # re-posted to WordPress. The seed-side 'posting' filter (candidate_row_ids)
    # only protects re-enqueues via Resume, not in-task redelivery.
    if await has_active_publish_job(db, run_id=run_id, row_id=row_id):
        return "skipped"

    target = await resolve_row_target(db, run=run, row_id=row_id)
    if isinstance(target, ResolveError):
        await _record_failure(
            db,
            run=run,
            row_id=row_id,
            error=target.message,
            domain_id_override=target.domain_id,
        )
        return "failed"

    domain = target.domain
    profile_name = target.profile_name

    fields = await _build_fields(db, run=run, row_id=row_id)

    try:
        media_cache = MediaCache(db, domain.id) if domain.cms_type == "wordpress" else None
        client = get_cms_client(domain, media_cache=media_cache)
    except UnsupportedCms as e:
        await _record_failure(
            db,
            run=run,
            row_id=row_id,
            error=str(e),
            domain_id_override=domain.id,
        )
        return "failed"

    limits = await resolve_for_domain(db, domain)
    limiter = get_rate_limiter()

    job = PublishJob(
        domain_id=domain.id,
        source_kind="bulk_row",
        source_ref={
            "run_id": run.id,
            "table_id": run.table_id,
            "row_id": row_id,
        },
        status="posting",
        language=run.language,
        profile_name=profile_name or None,
        created_by_id=run.created_by_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        async with limiter.acquire(
            provider_code=domain_rate_key(domain.id),
            max_concurrency=limits.max_concurrency,
            requests_per_minute=limits.requests_per_minute,
            inter_request_delay_ms=limits.inter_request_delay_ms,
        ):
            result = await client.publish_post(
                fields=fields,
                language=run.language,
                profile_name=profile_name or None,
            )
    except Exception as e:  # noqa: BLE001 — last-resort guard
        result = None
        crash_msg = f"{type(e).__name__}: {e}"
        job.payload_sent = None
        job.response_json = None
        job.error = crash_msg
        job.status = "failed"
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await _bump_counter(db, run_id=run.id, field="failed")
        await log_error(
            db,
            source="worker",
            category="publish_error",
            message=crash_msg,
            user_id=run.created_by_id,
            provider=None,
            context={
                "endpoint": "bulk_publish",
                "run_id": run.id,
                "domain_id": domain.id,
                "row_id": row_id,
                "mode": run.mode,
            },
            resource_type="bulk_publish_run",
            resource_id=run.id,
        )
        return "failed"

    job.payload_sent = result.payload_sent
    job.response_json = result.response_json
    job.cms_post_id = result.cms_post_id
    job.cms_post_url = result.cms_post_url
    job.warnings = list(result.warnings) if result.warnings else None
    job.finished_at = datetime.now(timezone.utc)

    if result.ok:
        job.status = "posted"
        await db.commit()
        await _writeback(db, run=run, row_id=row_id, result=result)
        await _bump_counter(db, run_id=run.id, field="done")
        return "posted"
    else:
        job.status = "failed"
        job.error = result.error
        await db.commit()
        await _bump_counter(db, run_id=run.id, field="failed")
        await log_error(
            db,
            source="worker",
            category="publish_error",
            message=result.error or "publish failed",
            user_id=run.created_by_id,
            provider=None,
            status_code=result.status_code,
            context={
                "endpoint": "bulk_publish",
                "run_id": run.id,
                "domain_id": domain.id,
                "domain_name": domain.name,
                "row_id": row_id,
                "mode": run.mode,
            },
            resource_type="bulk_publish_run",
            resource_id=run.id,
        )
        return "failed"


async def _build_fields(
    db: AsyncSession, *, run: BulkPublishRun, row_id: int
) -> dict[str, Any]:
    """Resolve {field_key → cell.value} from the run's field_to_column map."""
    field_map = run.field_to_column or {}
    if not field_map:
        return {}
    column_ids = {int(v) for v in field_map.values()}
    rows = (
        await db.execute(
            select(BulkTableCell.column_id, BulkTableCell.value).where(
                BulkTableCell.row_id == row_id,
                BulkTableCell.column_id.in_(column_ids),
            )
        )
    ).all()
    value_by_col = {col_id: (val or "") for col_id, val in rows}
    return {fkey: value_by_col.get(int(col_id), "") for fkey, col_id in field_map.items()}


async def _writeback(
    db: AsyncSession,
    *,
    run: BulkPublishRun,
    row_id: int,
    result,
) -> None:
    """Write cms_post_id and cms_post_url back into designated bulk columns."""
    targets: dict[str, str] = {}
    if (col := (run.back_fill or {}).get("post_id_target")) is not None and result.cms_post_id:
        targets[str(col)] = result.cms_post_id
    if (col := (run.back_fill or {}).get("post_url_target")) is not None and result.cms_post_url:
        targets[str(col)] = result.cms_post_url
    if not targets:
        return

    for col_str, value in targets.items():
        col_id = int(col_str)
        cell = (
            await db.execute(
                select(BulkTableCell).where(
                    BulkTableCell.row_id == row_id,
                    BulkTableCell.column_id == col_id,
                )
            )
        ).scalar_one_or_none()
        if cell is None:
            cell = BulkTableCell(
                row_id=row_id, column_id=col_id, status="manual", value=value
            )
            db.add(cell)
        else:
            cell.value = value
            cell.status = "manual"
            cell.error = None
    await db.commit()


async def _record_failure(
    db: AsyncSession,
    *,
    run: BulkPublishRun,
    row_id: int,
    error: str,
    domain_id_override: int | None = None,
) -> None:
    """Record a row-level failure as a publish_jobs row + bump the counter.

    `domain_id_override` lets multi-mode resolution attach the resolved
    domain to the failed job even when the run itself has no fixed domain
    (so the by-domain summary attributes the failure to the right site).
    """
    job = PublishJob(
        domain_id=domain_id_override if domain_id_override is not None else run.domain_id,
        source_kind="bulk_row",
        source_ref={
            "run_id": run.id,
            "table_id": run.table_id,
            "row_id": row_id,
        },
        status="failed",
        language=run.language,
        profile_name=run.profile_name or None,
        error=error,
        finished_at=datetime.now(timezone.utc),
        created_by_id=run.created_by_id,
    )
    db.add(job)
    await db.commit()
    await _bump_counter(db, run_id=run.id, field="failed")


_ALLOWED_BUMP_FIELDS = frozenset({"done", "failed", "skipped"})


async def _bump_counter(
    db: AsyncSession, *, run_id: int, field: str
) -> None:
    """Atomically increment one of run.done/failed/skipped + finalize when done.

    The column name is interpolated into raw SQL because SQLAlchemy parameter
    binding only works for values, not identifiers. We allow-list the names
    instead — currently every caller passes a literal so this is belt-and-
    braces, but it removes the footgun where a future change might hand
    user-controlled input to ``field``.
    """
    if field not in _ALLOWED_BUMP_FIELDS:
        raise ValueError(f"_bump_counter: field must be one of {_ALLOWED_BUMP_FIELDS}, got {field!r}")
    await db.execute(
        text(
            f"UPDATE bulk_publish_runs SET {field} = {field} + 1 WHERE id = :id"
        ),
        {"id": run_id},
    )
    # Finalize: terminal status + finished_at when total reached.
    await db.execute(
        text(
            "UPDATE bulk_publish_runs "
            "SET status = 'done', finished_at = now() "
            "WHERE id = :id "
            "AND status = 'running' "
            "AND done + failed + skipped >= total "
            "AND total > 0"
        ),
        {"id": run_id},
    )
    await db.commit()
