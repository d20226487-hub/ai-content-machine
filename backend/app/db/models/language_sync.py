"""SQLAlchemy models for the language-sync run + result tables.

Two-row pattern: one ``LanguageSyncRun`` row per batch (summary counts +
who triggered it), with N ``LanguageSyncResult`` rows hanging off it (one
per (run, target domain) attempt). Same shape as `publish_runs` +
`publish_jobs` so anyone who's seen one layout understands the other.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LanguageSyncRun(Base):
    __tablename__ = "language_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # ON DELETE SET NULL — deleting a user shouldn't wipe their sync
    # history. We keep the run, just lose the attribution.
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(40), default="bulk_modal", nullable=False)

    # Background-job lifecycle: 'queued' -> 'running' -> 'done'. Synchronous
    # historical runs (pre-0054) backfill to 'done'.
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="done", nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Bumped every batch so a stalled run can be detected.
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ok_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, nullable=False)

    results: Mapped[list["LanguageSyncResult"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LanguageSyncResult(Base):
    __tablename__ = "language_sync_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("language_sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    # ON DELETE SET NULL — deleting a domain shouldn't lose the history
    # of language syncs that targeted it. We keep the snapshot name in
    # `domain_name` for display purposes.
    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )
    domain_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # JSON array of language codes we attempted to upsert on this target.
    languages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # 'pending' = the worker hasn't attempted this target yet; 'done' = it has
    # (whatever the outcome — ok / fail / skip). Drives progress + lets
    # retry-failed flip a failed row back to 'pending' for re-attempt.
    state: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="done", nullable=False
    )

    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[LanguageSyncRun] = relationship(back_populates="results")
