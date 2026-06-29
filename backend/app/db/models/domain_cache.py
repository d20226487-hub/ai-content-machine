"""Domain cache runs — background bulk clear/warm of Custom-CMS site caches.

The Custom CMS exposes two cache-control endpoints on each site:
  * ``/index.php?_clear_cache``  — flush the cache
  * ``/index.php?__warm_cache``  — rebuild (warm) the cache

This model backs a background job (with a progress page, like Bulk Runs and
Autotool Runs) that fans out one ``domain_cache_run_items`` row per selected
Custom-CMS domain; a Celery worker hits the chosen endpoint(s) reusing the
domain's stored credentials and bumps the run counters, finalising when
done+failed+skipped reaches total.

WordPress domains do not have these endpoints (they publish via Autotool), so
non-Custom domains in a selection are excluded at creation — see
``skipped_unsupported``.
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


class DomainCacheRun(Base):
    __tablename__ = "domain_cache_runs"
    __table_args__ = (Index("ix_domain_cache_runs_status", "status"),)

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

    # 'clear' | 'warm' | 'clear_and_warm'
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    # 'queued' | 'running' | 'cancelled' | 'done' | 'failed'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Items left un-run by a Cancel. Counted in the finalize predicate
    # (done+failed+skipped >= total) so a cancelled-then-retried run still ends.
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Selected domains excluded at creation because they aren't Custom CMS
    # (or no longer exist). Not turned into items — purely informational so the
    # progress page can explain "N WordPress/unavailable domains were skipped".
    skipped_unsupported: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DomainCacheRunItem(Base):
    __tablename__ = "domain_cache_run_items"
    __table_args__ = (
        Index("ix_domain_cache_run_items_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("domain_cache_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SET NULL: a finished run's history outlives the domain. The snapshots
    # below keep the row readable even after the domain is renamed/deleted.
    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )
    domain_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    # 'queued' | 'running' | 'done' | 'failed' | 'skipped'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # HTTP status of each sub-step. NULL when the action didn't run that step
    # (e.g. warm_status_code stays NULL for a 'clear'-only run) or the request
    # never completed (network error — see ``detail``).
    clear_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warm_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
