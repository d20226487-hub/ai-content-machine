"""LinkCheckRun + LinkCheckViolation — bookkeeping for the link checker.

A run scans selected output column(s) for link problems via two optional
mechanisms (juxtapose against a per-row expected-links column; crawl for
HTTP status). Because crawling is network-bound, the work happens in a
Celery task with live progress — the worker consults ``status`` so a Cancel
stops in-flight crawling. Each flagged link becomes a LinkCheckViolation.

Schema mirrors ``bulk_generation_runs`` (status + counters + stamps) so the
editor reuses the same progress patterns. See migration 0034.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkCheckRun(Base):
    __tablename__ = "link_check_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # queued → running → (cancelled | done | failed)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    # Output columns to scan.
    column_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Expected-link columns (internal/external/product/…) unioned per row.
    # Empty = juxtapose has no source. A plain id list (no FK) — a deleted
    # column is simply filtered out at run time.
    expected_column_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    check_juxtapose: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    check_crawl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When crawling, also record healthy links (2xx/3xx) as rows so the
    # results table can show a full per-link status inventory.
    include_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Crawl progress: total unique links to fetch, and how many done.
    total_links: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Summary counters for the run header.
    ok_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    broken_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    omitted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hallucinated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class LinkCheckViolation(Base):
    __tablename__ = "link_check_violations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("link_check_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain ints (no FK): a later row/column delete shouldn't cascade away
    # the historical finding. Snapshots below keep the row renderable.
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_id: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # 'omitted' | 'hallucinated' | 'broken' | 'ok'
    problem: Mapped[str] = mapped_column(String(16), nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    # Stable code rendered + localized on the frontend:
    # 'expected_missing' | 'not_in_expected' | 'http_error' | 'timeout'
    # | 'unreachable' | 'blocked' | 'ok' | 'redirect'
    detail_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
