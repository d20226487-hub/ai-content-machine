"""StructureFormatRun + StructureFormatCell — the Structure & Formatting tool.

A user-selected subset of deterministic text transforms (markdown->HTML, strip
response-start junk, strip inline CSS, strip bold/italic/underline) is applied
across the chosen columns in a fixed order. Because a large table (5k+ rows)
would blow past the request timeout — and its revert snapshot would balloon —
the work runs as a background Celery job with live progress, mirroring the
Link Checker.

Each CANDIDATE cell becomes a ``StructureFormatCell`` (the unit of work AND,
for the ones that actually changed, the before/after snapshot for revert).
See migration 0041.
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


class StructureFormatRun(Base):
    __tablename__ = "structure_format_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The selected transforms (subset of the canonical OPERATIONS), in order.
    operations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # List[int] of column ids the run targeted (empty = all columns).
    column_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # queued → running → (done | failed | cancelled)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # Optional user-given label (NULL → UI shows a "<tool> #<id>" fallback).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Candidate cells to process; processed so far; failed.
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Distinct cells whose value actually changed (set on finalize).
    cell_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # NULL = applied; set when the run's writes were reverted.
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class StructureFormatCell(Base):
    __tablename__ = "structure_format_cells"
    __table_args__ = (
        UniqueConstraint("run_id", "row_id", "column_id", name="uq_sfc_run_row_col"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("structure_format_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain ints (no FK): a later row/column delete shouldn't cascade away the
    # historical record. column_name snapshot keeps the row renderable.
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_id: Mapped[int] = mapped_column(Integer, nullable=False)
    column_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # pending → done (changed) | skipped (no change) | failed. Re-querying
    # pending makes the worker idempotent under redelivery / resume.
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    # Set only for 'done' cells — the before/after used for the diff + revert.
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Subset of the run's transforms that actually changed THIS cell (for the
    # run-page filter). Empty for skipped cells.
    applied_ops: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
