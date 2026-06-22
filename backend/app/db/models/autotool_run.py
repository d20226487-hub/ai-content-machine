"""Autotool send runs — a persisted, background version of the per-domain-page
ImportPosts POSTs.

Replaces the old synchronous "fire all, show inline" send. Each run fans out
one ``autotool_run_items`` row per (domain, page); a Celery worker fires each
POST and bumps the run's counters, finalising when sent+failed reaches total.
Mirrors the bulk-publish run shape, but leaner — Autotool items are quick
external POSTs, so there's no pause/resume, just Cancel + Retry-failed.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutotoolRun(Base):
    __tablename__ = "autotool_runs"
    __table_args__ = (Index("ix_autotool_runs_status", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # SET NULL (not CASCADE): a finished run's history outlives its table.
    table_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshots taken at creation so the run reads sensibly even if the table is
    # later renamed/deleted or the target URL is changed.
    table_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    target_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")

    site_column_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # 'queued' | 'running' | 'cancelled' | 'done' | 'failed'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Items left unsent by a Cancel. Counted in the finalize predicate
    # (sent+failed+skipped >= total) so a cancelled-then-retried run still ends.
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutotoolRunItem(Base):
    __tablename__ = "autotool_run_items"
    __table_args__ = (Index("ix_autotool_run_items_run_status", "run_id", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("autotool_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site: Mapped[str] = mapped_column(String(2048), nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # domain total
    file_token: Mapped[str] = mapped_column(Text, nullable=False)

    # 'queued' | 'sending' | 'sent' | 'failed' | 'skipped'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
