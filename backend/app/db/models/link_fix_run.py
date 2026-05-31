"""LinkFixRun + LinkFixCell — the AI link-fix pass for the Link Checker.

After a check run flags problems, the user picks rows (or all) and an LLM
rewrites ONLY the links in each flagged output cell per the Brain
``fix_links`` prompt. The work is distributed (one ``LinkFixCell`` per
flagged cell, processed by a Celery fan-out) and revertable (each cell
keeps an old/new snapshot). When the run finishes it auto-creates a
row-scoped ``LinkCheckRun`` (``recheck_run_id``) so the user sees what,
if anything, is still wrong.

Mirrors the bulk_generation / link_check run shape (status + counters +
stamps) so the editor reuses the same polling/progress patterns. See
migration 0037.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkFixRun(Base):
    __tablename__ = "link_fix_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The check run this fix was launched from (SET NULL so purging a check
    # run doesn't drop the fix history).
    source_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("link_check_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The scoped LinkCheckRun auto-created on finish (residual problems).
    recheck_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("link_check_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # queued → running → (cancelled | done | failed)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    # Optional user-given label (NULL → UI shows a "<tool> #<id>" fallback).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Column the corrected content is written to. NULL = overwrite the source
    # column. Set to a different (often new) column to preserve the original.
    target_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )

    # Snapshot of the source run's column config (scan + expected columns) so
    # the worker + auto re-check don't depend on the mutable check run.
    column_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_column_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # NULL = applied; set when the run's writes were reverted.
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class LinkFixCell(Base):
    __tablename__ = "link_fix_cells"
    __table_args__ = (
        UniqueConstraint("run_id", "row_id", "column_id", name="uq_lfc_run_row_col"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("link_fix_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain ints (no FK): a later row/column delete shouldn't cascade away the
    # historical fix. column_name snapshot keeps the row renderable.
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_id: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # pending → done | failed | skipped (re-query pending = idempotent).
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    # Original SOURCE content (for the before/after display). Distinct from
    # old_value, which snapshots the TARGET cell's pre-write value for revert
    # (the two differ when correcting into a separate column).
    source_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The flagged links fed to the AI:
    #   [{problem, link, detail_code, status_code}, …]
    violations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
