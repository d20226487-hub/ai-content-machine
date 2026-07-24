"""On-demand aggregation of every in-flight background job, across all users.

This backs the dashboard "Active processes" card. It is deliberately pull-only:
one call runs one small query per job table (filtered to the queued/running/
paused rows, which are inherently few), normalises each row to an ``ActivityItem``
and returns a snapshot. Nothing here polls or caches — the client fetches when
the operator clicks "Check now", so there is no standing load on the server.

Adding a new job type = add one ``_Source`` row below (model, kind, which status
values count as in-flight, and how to read its label / progress / detail link).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutotoolRun,
    BackupRun,
    BulkGenerationRun,
    BulkPublishRun,
    CsvExportJob,
    DomainCacheRun,
    GdocsImportRun,
    LanguageSyncRun,
    LinkCheckRun,
    LinkFixRun,
    StructureFormatRun,
    User,
)
from app.schemas.dashboard import ActivityItem, ActivityResponse

_MAX_ITEMS = 500  # backstop; in-flight rows are inherently bounded


@dataclass(frozen=True)
class _Source:
    model: type
    kind: str
    active: tuple[str, ...]  # status values that count as "in flight"
    label: Callable[[Any], str]
    # row -> (done, total); either may be None when the job exposes no progress
    progress: Callable[[Any], tuple[int | None, int | None]]
    detail: Callable[[Any], str | None]
    owner: bool = True  # has a created_by_id


def _named(row: Any, prefix: str) -> str:
    """`name` if the run has one, else a stable "<prefix> #<id>" fallback."""
    return (getattr(row, "name", None) or "").strip() or f"{prefix} #{row.id}"


def _sum(*vals: int | None) -> int:
    return sum(v or 0 for v in vals)


# One row per job type. Progress "done" folds terminal per-item counters
# (done+failed+skipped) so the bar reflects everything the worker has finished,
# not just successes.
_SOURCES: tuple[_Source, ...] = (
    _Source(
        AutotoolRun, "autotool", ("queued", "running"),
        label=lambda r: r.table_name,
        progress=lambda r: (_sum(r.sent, r.failed, r.skipped), r.total),
        detail=lambda r: f"/publish/autotool/runs/{r.id}",
    ),
    _Source(
        BulkGenerationRun, "generation", ("queued", "running"),
        label=lambda r: _named(r, "Generation"),
        progress=lambda r: (_sum(r.done, r.failed, r.skipped), r.total),
        detail=lambda r: f"/library/gen-runs/{r.id}",
    ),
    _Source(
        BulkPublishRun, "publish", ("queued", "running", "paused"),
        label=lambda r: _named(r, "Publish"),
        progress=lambda r: (_sum(r.done, r.failed, r.skipped), r.total),
        detail=lambda r: f"/publish/runs/{r.id}",
    ),
    _Source(
        GdocsImportRun, "gdocs_import", ("queued", "running"),
        label=lambda r: r.table_name,
        progress=lambda r: (r.docs_done, r.total_docs),
        detail=lambda r: f"/library/import/gdocs/{r.id}",
    ),
    _Source(
        DomainCacheRun, "domain_cache", ("queued", "running"),
        label=lambda r: r.action,
        progress=lambda r: (_sum(r.done, r.failed, r.skipped), r.total),
        detail=lambda r: f"/publish/cache/runs/{r.id}",
    ),
    _Source(
        LanguageSyncRun, "language_sync", ("queued", "running"),
        label=lambda r: r.source,
        progress=lambda r: (_sum(r.ok_count, r.fail_count, r.skip_count), r.total_count),
        detail=lambda r: f"/publish/languages/{r.id}",
    ),
    _Source(
        LinkCheckRun, "link_check", ("queued", "running"),
        label=lambda r: _named(r, "Link-Check"),
        progress=lambda r: (r.crawled, r.total_links),
        detail=lambda r: f"/library/{r.table_id}/link-check/runs/{r.id}",
    ),
    _Source(
        LinkFixRun, "link_fix", ("queued", "running"),
        label=lambda r: _named(r, "Link-Fix"),
        progress=lambda r: (_sum(r.done, r.failed, r.skipped), r.total),
        detail=lambda r: f"/library/{r.table_id}/link-fix/runs/{r.id}",
    ),
    _Source(
        StructureFormatRun, "structure_format", ("queued", "running"),
        label=lambda r: _named(r, "Structure"),
        progress=lambda r: (_sum(r.done, r.failed), r.total),
        detail=lambda r: f"/library/{r.table_id}/structure-format/runs/{r.id}",
    ),
    _Source(
        CsvExportJob, "csv_export", ("queued", "running"),
        label=lambda r: (r.table_name or r.filename or "").strip(),
        progress=lambda r: (r.rows_done, r.rows_total),
        detail=lambda r: None,
    ),
    _Source(
        BackupRun, "backup", ("running",),  # backups have no queued state
        label=lambda r: (r.filename or "").strip(),
        progress=lambda r: (None, None),
        detail=lambda r: None,
        owner=False,
    ),
)

# running (and paused, an in-progress-but-suspended state) sort above queued.
_STATUS_ORDER = {"running": 0, "paused": 1, "queued": 2}


async def list_active_processes(db: AsyncSession) -> ActivityResponse:
    """Snapshot of every queued/running/paused job across all users."""
    collected: list[tuple[_Source, Any]] = []
    owner_ids: set[int] = set()
    for src in _SOURCES:
        rows = (
            await db.execute(select(src.model).where(src.model.status.in_(src.active)))
        ).scalars().all()
        for r in rows:
            collected.append((src, r))
            if src.owner and getattr(r, "created_by_id", None) is not None:
                owner_ids.add(r.created_by_id)

    owners: dict[int, str] = {}
    if owner_ids:
        owners = {
            uid: (full_name or email)
            for uid, full_name, email in (
                await db.execute(
                    select(User.id, User.full_name, User.email).where(
                        User.id.in_(owner_ids)
                    )
                )
            ).all()
        }

    items: list[ActivityItem] = []
    for src, r in collected:
        done, total = src.progress(r)
        started = getattr(r, "started_at", None)
        created = getattr(r, "created_at", None) or started
        oid = getattr(r, "created_by_id", None) if src.owner else None
        items.append(
            ActivityItem(
                kind=src.kind,
                id=r.id,
                label=src.label(r) or "",
                owner=owners.get(oid) if oid is not None else None,
                status=r.status,
                done=done,
                total=total,
                started_at=started,
                created_at=created,
                detail_path=src.detail(r),
            )
        )

    # In-flight first (running/paused before queued), newest first within.
    items.sort(
        key=lambda it: (
            _STATUS_ORDER.get(it.status, 9),
            -(it.created_at.timestamp() if it.created_at else 0.0),
        )
    )
    return ActivityResponse(
        items=items[:_MAX_ITEMS], checked_at=datetime.now(timezone.utc)
    )
