"""Background CSV export jobs — build the table CSV in a worker, store it
gzipped, then let the browser download the pre-built blob.

Why: a synchronous ``GET .../export.csv`` keeps one HTTP request open for the
whole build+transfer, which trips the front proxy/CDN response timeout on large
tables. Here the build runs in Celery (no HTTP clock) and the download serves an
already-built blob (instant first byte). See app/db/models/csv_export.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BulkTable,
    BulkTableColumn,
    BulkTableRow,
    CsvExportBlob,
    CsvExportJob,
    User,
)
from app.schemas.csv_export import CsvExportJobRead
from app.services.bulk_csv import build_table_csv_gzip

# Prepared exports are throwaway artifacts — a daily beat task deletes jobs (and
# their blobs, via FK CASCADE) older than this.
_RETENTION_HOURS = 24
# Persist progress every N batches so a huge export updates the bar without a
# commit per 1,000 rows.
_PROGRESS_EVERY_BATCHES = 5


def _safe_filename(name: str) -> str:
    base = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
    return (base or "table") + ".csv"


def to_read(job: CsvExportJob) -> CsvExportJobRead:
    return CsvExportJobRead(
        id=job.id,
        table_id=job.table_id,
        table_name=job.table_name,
        filename=job.filename,
        status=job.status,
        rows_total=job.rows_total,
        rows_done=job.rows_done,
        byte_size=job.byte_size,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _can_view(job: CsvExportJob, actor: User) -> bool:
    """A job is viewable/downloadable by its creator, or any admin/manager
    (who can read every table anyway)."""
    return job.created_by_id == actor.id or actor.role.name in {"admin", "manager"}


# ----- create / read (API) -----


async def create_job(
    db: AsyncSession, table: BulkTable, actor: User
) -> CsvExportJob:
    """Insert a queued export job for ``table``. Caller enqueues the build task."""
    job = CsvExportJob(
        table_id=table.id,
        table_name=table.name,
        filename=_safe_filename(table.name),
        status="queued",
        created_by_id=actor.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: int, actor: User) -> CsvExportJob:
    job = await db.get(CsvExportJob, job_id)
    if job is None or not _can_view(job, actor):
        raise HTTPException(status_code=404, detail="Export job not found")
    return job


async def load_blob_for_download(
    db: AsyncSession, job_id: int, actor: User
) -> tuple[bytes, str]:
    """Return ``(gzipped_bytes, filename)`` for a finished job, enforcing ACL."""
    job = await get_job(db, job_id, actor)
    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Export is not ready (status: {job.status}).",
        )
    blob = (
        await db.execute(
            select(CsvExportBlob.content_gzip).where(CsvExportBlob.job_id == job_id)
        )
    ).scalar_one_or_none()
    if blob is None:
        raise HTTPException(status_code=404, detail="Export file is no longer available.")
    return blob, job.filename


# ----- build (Celery worker) -----


async def build_job(db: AsyncSession, job_id: int) -> str:
    """Build the CSV, gzip it, and store the blob. Idempotent via a guarded
    queued->running claim, so a redelivered task is a no-op."""
    job = await db.get(CsvExportJob, job_id)
    if job is None or job.status != "queued":
        return "not_queued"

    now = datetime.now(timezone.utc)
    claim = await db.execute(
        update(CsvExportJob)
        .where(CsvExportJob.id == job_id, CsvExportJob.status == "queued")
        .values(status="running", started_at=now)
    )
    await db.commit()
    if (claim.rowcount or 0) != 1:
        return "not_queued"

    try:
        job = await db.get(CsvExportJob, job_id)
        table = (
            await db.get(BulkTable, job.table_id) if job.table_id is not None else None
        )
        if table is None or table.deleted_at is not None:
            raise ValueError("The table no longer exists.")

        col_rows = (
            await db.execute(
                select(BulkTableColumn.id, BulkTableColumn.name)
                .where(BulkTableColumn.table_id == table.id)
                .order_by(BulkTableColumn.position, BulkTableColumn.id)
            )
        ).all()
        columns = [(c.id, c.name) for c in col_rows]

        total = (
            await db.execute(
                select(func.count())
                .select_from(BulkTableRow)
                .where(BulkTableRow.table_id == table.id)
            )
        ).scalar_one()
        await db.execute(
            update(CsvExportJob)
            .where(CsvExportJob.id == job_id)
            .values(rows_total=int(total))
        )
        await db.commit()

        # Throttled progress: persist every Nth batch.
        counter = {"batches": 0}

        async def on_progress(done: int) -> None:
            counter["batches"] += 1
            if counter["batches"] % _PROGRESS_EVERY_BATCHES == 0:
                await db.execute(
                    update(CsvExportJob)
                    .where(CsvExportJob.id == job_id)
                    .values(rows_done=done)
                )
                await db.commit()

        blob, rows = await build_table_csv_gzip(
            db, table.id, columns, on_progress=on_progress
        )

        db.add(CsvExportBlob(job_id=job_id, content_gzip=blob))
        await db.execute(
            update(CsvExportJob)
            .where(CsvExportJob.id == job_id)
            .values(
                status="done",
                rows_done=rows,
                byte_size=len(blob),
                finished_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        return "done"
    except Exception as e:  # noqa: BLE001 — record the failure on the job
        await db.rollback()
        await db.execute(
            update(CsvExportJob)
            .where(CsvExportJob.id == job_id)
            .values(
                status="failed",
                error=str(e)[:500],
                finished_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        raise


# ----- cleanup (beat) -----


async def cleanup_old_jobs(db: AsyncSession) -> int:
    """Delete export jobs (and their blobs, via FK CASCADE) older than the
    retention window. Returns how many job rows were removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_RETENTION_HOURS)
    res = await db.execute(
        delete(CsvExportJob).where(CsvExportJob.created_at < cutoff)
    )
    await db.commit()
    return int(res.rowcount or 0)
