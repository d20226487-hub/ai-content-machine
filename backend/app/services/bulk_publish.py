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

# Field keys whose value is treated as a slug / URL path and gets its
# surrounding slashes stripped before being sent to a Custom CMS upstream.
# Operators routinely paste path-style values into bulk-table slug columns
# (`/fr/`, `/where-to-watch/`, `/live-stream`). WP's REST API auto-runs
# sanitize_title server-side and strips the slashes for us; Custom CMS has
# no such guarantee, so the same cell that publishes cleanly to WP would
# create double-slash URLs (or worse, get stored verbatim and break later
# slug lookups) on a Custom site. Normalizing to bare-slug here is the
# Custom-side analog of WP's server-side sanitizer.
#
# Scoped to known slug-like keys rather than every field — we don't want
# to silently rewrite an HTML or text field that happens to contain a
# leading slash. Match is case-insensitive against `field_to_column` keys.
_CUSTOM_CMS_SLUG_LIKE_FIELDS = frozenset(
    {"slug", "url", "permalink", "path", "post_slug"}
)


# ---------- per-row target resolution ----------


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    domain: Domain
    profile_name: str  # '' for Custom CMS or "use default" in WP
    # Per-row resolved language (multi mode + language_column_id set).
    # None means "use the run-level language" — single mode always ends
    # up here, and multi mode without a language column also.
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ResolveError:
    message: str  # surfaced to the publish_jobs.error column
    domain_id: int | None = None  # set if we resolved domain but failed later


async def _resolve_row_language(
    db: AsyncSession, *, run: BulkPublishRun, row_id: int, domain: Domain
) -> str | None | ResolveError:
    """Resolve the per-row language when ``run.language_column_id`` is set.

    Returns:
      * the canonical language string from ``domain.languages`` on success,
      * ``None`` when no language column is configured (caller falls back
        to ``run.language``),
      * ``ResolveError`` when the cell is empty or the value isn't in
        the domain's configured languages (strict mode — empty fails).

    Works the same way for single + multi mode runs since both end up
    here with a resolved ``domain``.
    """
    if run.language_column_id is None:
        return None
    lang_raw = await _read_cell_value(
        db, row_id=row_id, column_id=run.language_column_id
    )
    if not lang_raw:
        return ResolveError(
            message=(
                "Language column is empty for this row. When a per-row "
                "Language column is set, every row must have a value "
                "(no fallback to the run-level language in strict mode)."
            ),
            domain_id=domain.id,
        )
    # Normalize: lowercase + trim. Domain.languages stores codes as
    # the operator entered them; match case-insensitively, then
    # return the canonical form from the domain config so downstream
    # comparisons / display use the same string.
    normalized = lang_raw.strip().lower()
    domain_langs = domain.languages or []
    canonical = next(
        (l for l in domain_langs if (l or "").strip().lower() == normalized),
        None,
    )
    if canonical is None:
        available = ", ".join(repr(l) for l in domain_langs) or "(none configured)"
        return ResolveError(
            message=(
                f"Language {lang_raw!r} is not configured on domain "
                f"{domain.name!r}. Available: {available}."
            ),
            domain_id=domain.id,
        )
    return canonical


async def resolve_row_target(
    db: AsyncSession, *, run: BulkPublishRun, row_id: int
) -> ResolvedTarget | ResolveError:
    """Decide where this row should publish.

    Single mode: returns the run-level (domain, profile_name).
    Multi mode: reads cells from run.domain_column_id / .profile_column_id,
    looks up domain by name. Both WordPress and Custom CMS domains are
    accepted — for Custom CMS rows we just skip profile resolution
    (Custom CMS has no profiles concept) and the per-row publish branches
    on ``domain.cms_type`` further down. If the run's ``field_to_column``
    map doesn't cover a particular Custom CMS site's template fields,
    that row will fail individually with a clear field-name error — the
    same per-row failure model WordPress already uses.

    In BOTH modes, if ``run.language_column_id`` is set, the per-row
    language is read from the cell and validated against the resolved
    domain's ``languages[]`` — empty cell or unknown language fails the
    row.
    """
    if run.mode == "single":
        if run.domain_id is None:
            return ResolveError(message="Domain has been deleted; cannot publish.")
        domain = await db.get(Domain, run.domain_id)
        if domain is None:
            return ResolveError(message="Domain has been deleted; cannot publish.")
        if domain.deleted_at is not None:
            # Race: the run was created while the domain was active,
            # then the domain got trashed before the worker reached us.
            # The trash endpoint blocks this for in-flight runs, but
            # defense-in-depth here keeps us from publishing to a
            # trashed domain even if the race window slipped through.
            return ResolveError(
                message=f"Domain {domain.name!r} has been moved to Trash; cannot publish.",
                domain_id=domain.id,
            )
        lang_result = await _resolve_row_language(
            db, run=run, row_id=row_id, domain=domain
        )
        if isinstance(lang_result, ResolveError):
            return lang_result
        return ResolvedTarget(
            domain=domain,
            profile_name=run.profile_name or "",
            language=lang_result,
        )

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

    # Lookup by exact name among ACTIVE domains only. Trashed domains
    # with the same name are invisible — the partial unique index added
    # in migration 0023 lets a trashed and an active domain share a name
    # (e.g. you trashed "Site A" and recreated a new "Site A").
    domain = (
        await db.execute(
            select(Domain).where(
                Domain.name == domain_value, Domain.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if domain is None:
        return ResolveError(message=f"Domain not found: {domain_value!r}.")

    # Profile resolution. Profiles are a WordPress-only concept (Custom
    # CMS publishes through a single body_template, no profile branching),
    # so for Custom CMS rows we always leave profile_name = "" regardless
    # of whether the run carries a profile_column_id. This matches Single
    # mode behavior — a Custom CMS run never has a profile_name. It also
    # makes mixed-CMS tables (WP + Custom rows in one table) workable:
    # the WP rows use the profile column, the Custom rows ignore it.
    profile_name = ""
    if domain.cms_type == "wordpress" and run.profile_column_id is not None:
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

    lang_result = await _resolve_row_language(
        db, run=run, row_id=row_id, domain=domain
    )
    if isinstance(lang_result, ResolveError):
        return lang_result

    return ResolvedTarget(
        domain=domain, profile_name=profile_name, language=lang_result,
    )


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
    # Effective per-row language: when the run has a language_column_id,
    # resolver returns the resolved cell value (already validated against
    # domain.languages). Otherwise fall back to the run-level language.
    effective_language = target.language if target.language is not None else run.language

    # CMS-vs-operation compatibility: defense in depth. The API layer
    # already rejected upsert/non-WP combinations at run creation; this
    # catches the case where a domain's cms_type changes between creation
    # and the worker picking up the row.
    if run.operation == "upsert" and domain.cms_type != "custom":
        await _record_failure(
            db,
            run=run,
            row_id=row_id,
            error=(
                f"Upsert is supported only for Custom CMS domains "
                f"(domain {domain.name!r} is {domain.cms_type})."
            ),
            domain_id_override=domain.id,
        )
        return "failed"

    fields = await _build_fields(db, run=run, row_id=row_id)

    # Custom CMS treats the operation as a per-row `action` field on the
    # outgoing JSON. The body_template author writes "{{action}}" in their
    # template; we inject the value here so the user doesn't have to add
    # an action column to every bulk table. WP handles operation via the
    # find_post → update_post / publish_post branching below.
    if domain.cms_type == "custom":
        fields.setdefault("action", run.operation)
        # Strip surrounding slashes from slug-like fields so values like
        # `/where-to-watch/`, `/fr/`, or `/live-stream` go on the wire as
        # bare slugs. See the constant's comment above for the full
        # rationale (WP normalizes server-side, Custom CMS does not).
        # We only touch values that actually have leading or trailing
        # slashes — `where-to-watch` passes through untouched.
        for fkey in list(fields.keys()):
            if fkey.lower() in _CUSTOM_CMS_SLUG_LIKE_FIELDS:
                raw = fields[fkey]
                if isinstance(raw, str) and raw and (
                    raw.startswith("/") or raw.endswith("/")
                ):
                    fields[fkey] = raw.strip("/")
        # For Custom CMS, the per-row language already lives in the body
        # (via field_to_column['lang']). Carry it into PublishJob.language
        # too so the run-detail UI Lang column matches reality, instead of
        # showing the run-level fallback everywhere.
        lang_from_field = (fields.get("lang") or "").strip()
        if lang_from_field:
            effective_language = lang_from_field

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

    # ===== Create mode: optional pre-check for slug duplicates =====
    #
    # When the operator turned on `on_slug_conflict` (skip / update), we
    # peek at the WP side BEFORE allocating a publish_job. The pre-check
    # uses the same find_post call we use in Update mode, so it's
    # language-aware via Polylang/WPML ?lang=… — an EN canada doesn't
    # block a new RU canada.
    update_post_id: int | None = None
    if run.operation == "create" and run.on_slug_conflict != "create":
        slug_value = str(fields.get("slug") or "").strip()
        if slug_value and domain.cms_type == "wordpress":
            # Reuse the WP client (already built above) — it has the
            # correct auth + UA + transport. find_post handles URL-style
            # slugs and the view→edit context fallback.
            post_type, _defs = client._resolve_profile(profile_name)
            try:
                pre = await client.find_post(
                    post_type=post_type,
                    lookup_kind="slug",
                    value=slug_value,
                    language=effective_language,
                )
            except Exception:  # noqa: BLE001 — last-resort guard
                pre = None  # treat lookup crash as "no duplicate", same as 'find_post' returning a structured error
            # On a structured failure (WAF block, etc.) we don't know if a
            # duplicate exists. Fall through to the normal POST — at worst
            # WP auto-suffixes. The user sees the WAF errors elsewhere
            # (Update mode) and can fix Cloudflare first.
            if pre is not None and pre.post_id is not None:
                if run.on_slug_conflict == "skip":
                    # Record as a skipped publish_job (status='skipped'
                    # is a valid value — see JobStatus literal). The run
                    # detail per-row table shows it with a neutral badge.
                    job = PublishJob(
                        domain_id=domain.id,
                        source_kind="bulk_row",
                        source_ref={
                            "run_id": run.id,
                            "table_id": run.table_id,
                            "row_id": row_id,
                            "skipped_reason": "slug_exists",
                            "existing_post_id": pre.post_id,
                        },
                        status="skipped",
                        language=effective_language,
                        profile_name=profile_name or None,
                        error=(
                            f"Slug {slug_value!r} already exists on "
                            f"{domain.name} (post #{pre.post_id}) — skipped"
                        ),
                        finished_at=datetime.now(timezone.utc),
                        created_by_id=run.created_by_id,
                    )
                    db.add(job)
                    await db.commit()
                    await _bump_counter(db, run_id=run.id, field="skipped")
                    return "skipped"
                else:
                    # on_slug_conflict='update' → switch to PATCH on the
                    # existing post. The rest of publish_one_row already
                    # branches on `update_post_id is not None`.
                    update_post_id = pre.post_id

    # Update mode: resolve the existing post id before we allocate the
    # publish_job row. A lookup miss is a per-row failure and the row never
    # reaches WP — keeping the failed row out of `posting` simplifies the
    # state machine and shortens the audit trail.
    #
    # WP-only: Custom CMS update sends `id` in the body and lets the
    # upstream do the resolution server-side. No find_post pre-flight.
    if run.operation == "update" and domain.cms_type == "wordpress":
        if run.lookup_column_id is None or run.lookup_kind is None:
            await _record_failure(
                db,
                run=run,
                row_id=row_id,
                error=(
                    "Update run is missing lookup_kind or lookup_column_id "
                    "(column may have been deleted). Cancel the run and "
                    "start a new one."
                ),
                domain_id_override=domain.id,
            )
            return "failed"
        lookup_value = await _read_cell_value(
            db, row_id=row_id, column_id=run.lookup_column_id
        )
        if not lookup_value:
            await _record_failure(
                db,
                run=run,
                row_id=row_id,
                error=f"Update lookup column is empty for this row ({run.lookup_kind}).",
                domain_id_override=domain.id,
            )
            return "failed"
        post_type, _defs = client._resolve_profile(profile_name)
        try:
            lookup = await client.find_post(
                post_type=post_type,
                lookup_kind=run.lookup_kind,
                value=lookup_value,
                # Pass language so Polylang / WPML filter the lookup. Without
                # this a site with the same slug in two languages (e.g. EN
                # `canada` + RU `canada`) would silently update whichever
                # one Polylang surfaced first — usually the default language.
                # `effective_language` honors a per-row language_column_id
                # when set, otherwise falls back to the run-level language.
                language=effective_language,
            )
        except Exception as e:  # noqa: BLE001 — last-resort guard
            await _record_failure(
                db,
                run=run,
                row_id=row_id,
                error=(
                    f"Lookup crashed on {domain.name} "
                    f"({run.lookup_kind}={lookup_value!r}): "
                    f"{type(e).__name__}: {e}"
                ),
                domain_id_override=domain.id,
            )
            return "failed"
        if lookup.post_id is None:
            if lookup.error:
                # Structured failure: WAF block, HTTP error, malformed
                # JSON. Surface the real reason instead of "not found".
                msg = (
                    f"Lookup failed on {domain.name} "
                    f"({run.lookup_kind}={lookup_value!r}): {lookup.error}"
                )
            else:
                msg = (
                    f"Existing post not found on {domain.name} "
                    f"({run.lookup_kind}={lookup_value!r})."
                )
            await _record_failure(
                db, run=run, row_id=row_id, error=msg,
                domain_id_override=domain.id,
            )
            return "failed"
        update_post_id = lookup.post_id

    limits = await resolve_for_domain(db, domain)
    limiter = get_rate_limiter()

    job = PublishJob(
        domain_id=domain.id,
        source_kind="bulk_row",
        source_ref={
            "run_id": run.id,
            "table_id": run.table_id,
            "row_id": row_id,
            **({"operation": "update", "post_id": update_post_id} if update_post_id else {}),
        },
        status="posting",
        language=effective_language,
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
            if update_post_id is not None:
                result = await client.update_post(
                    post_id=update_post_id,
                    fields=fields,
                    language=effective_language,
                    profile_name=profile_name or None,
                )
            else:
                result = await client.publish_post(
                    fields=fields,
                    language=effective_language,
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
    # Migration 0026: persist the exact upstream HTTP code. CMS clients
    # already capture this on PublishResult; previously it was thrown
    # away after the function returned, leaving only the inferable "2xx
    # because we landed in the success branch" for posted rows.
    job.status_code = result.status_code
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
    """Resolve {field_key → cell.value} from the run's field_to_column map.

    Cell values are ``.strip()``-ed before being placed in the dict. CSV
    imports, copy/paste from Excel, and the bulk-table editor all leak
    trailing/leading newlines into cells, which then go out verbatim in
    publish bodies (we've seen `slug='home2\n'`, `action='\ncreate'`,
    `lang='en\n'`). Most CMSes either reject these outright or, worse,
    accept them and store the whitespace, breaking lookups by id/slug
    later. Stripping on publish leaves the editor data unchanged but
    keeps the wire-format clean.
    """
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
    value_by_col = {col_id: (val or "").strip() for col_id, val in rows}
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
