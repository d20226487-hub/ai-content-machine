"""Background CSV export jobs.

The synchronous ``GET /library/tables/{id}/export.csv`` streams fine from the
api, but for very large tables a single long-lived HTTP download trips the
response timeout of whatever proxy/CDN sits in front of prod (~100-120s). So
the table-page export is decoupled: a Celery worker builds the CSV (reusing the
keyset-batched streamer), gzips it, and stores the bytes here; the browser then
downloads the already-built blob in a fast separate request that can't time out.

The CSV is stored GZIPPED (a 70 MB CSV compresses to ~14 MB) in a separate
``csv_export_blobs`` table so polling the job status never drags the blob along.
Storing in the DB (vs a shared volume) keeps deployment to "pull + rebuild +
migrate" — no compose/volume coordination.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CsvExportJob(Base):
    __tablename__ = "csv_export_jobs"
    __table_args__ = (
        Index("ix_csv_export_jobs_status", "status"),
        Index("ix_csv_export_jobs_created_by", "created_by_id"),
        Index("ix_csv_export_jobs_table", "table_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # SET NULL: a finished export outlives its table. ``table_name`` /
    # ``filename`` snapshots keep the job readable afterwards.
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="SET NULL"), nullable=True
    )
    table_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Download filename, e.g. "My_Table.csv".
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # 'queued' | 'running' | 'done' | 'failed'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Size of the stored gzipped blob (bytes). NULL until done.
    byte_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CsvExportBlob(Base):
    """The gzipped CSV bytes for a finished job. Separate table so job-status
    polling never loads the (potentially tens-of-MB) blob. CASCADE so deleting
    the job (cleanup) drops the bytes with it."""

    __tablename__ = "csv_export_blobs"

    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("csv_export_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_gzip: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
