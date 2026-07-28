"""AiHelperRun + AiHelperCell — the general bulk-table "AI helper" mini-tool.

The operator gives a prompt (typed or from the library) + maps ``{{columns}}``,
picks Read (write to a target column) or Edit (rewrite in place), and every
selected row gets one AI call. The work is distributed (one ``AiHelperCell`` per
row, processed by a Celery fan-out through the provider rate limiter) and
revertable (each cell keeps an old/new snapshot). Mirrors the link-fix /
bulk-generation run shape so the editor reuses the same polling/progress/revert
patterns. See migration 0069.
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


class AiHelperRun(Base):
    __tablename__ = "ai_helper_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # queued → running → (cancelled | done | failed)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    # v1 single-output mode: 'read' (write to a target column) | 'edit' (rewrite
    # in place). Retained for legacy runs; v1.1 runs use ``outputs`` instead.
    mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="read", server_default="read"
    )
    # v1.1 fan-out engine: 'structured' (one AI call/row returning a JSON object
    # whose keys route to the output columns — cheapest, default) | 'per_output'
    # (one focused AI call per output column).
    engine: Mapped[str] = mapped_column(
        String(16), nullable=False, default="structured", server_default="per_output"
    )
    # Optional user label (NULL → UI shows a "<tool> #<id>" fallback).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # The task prompt, snapshotted (contains {{var}} placeholders). For the
    # structured engine this is the shared base prompt; for per_output it is the
    # first output's prompt (kept for the run summary — each output has its own).
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Provenance if loaded from the library (SET NULL keeps the snapshot).
    prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    # {var_name: source_column_id} — the input columns the prompt reads.
    variable_map: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # v1 single-output target (legacy). Read: column written; Edit: column
    # rewritten. v1.1 uses ``outputs`` — this stays NULL for new multi-out runs.
    target_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    # v1.1 output columns: list of
    # ``{"column_id": int, "mode": "write"|"edit", "key": str, "prompt": str}``.
    # ``key`` routes the structured engine's JSON; ``prompt`` is the per-output
    # prompt for the per_output engine. Empty for legacy runs (synthesized from
    # target_column_id/mode on read). Column ids are unique within the list.
    outputs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Per-run AI config (NULL = first-enabled provider + its default model).
    provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Input word-slice. 'full' | 'first_pct'; when 'first_pct', only the first
    # ``input_pct``% of ``slice_column_id``'s words (rounded to an HTML block
    # boundary) is sent, and Edit mode splices the reply back onto the remainder.
    input_scope: Mapped[str] = mapped_column(
        String(12), nullable=False, default="full", server_default="full"
    )
    input_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slice_column_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Rows this run targets (selection / range / filter), snapshotted.
    row_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # NULL = applied; set when the run's writes were reverted (edit mode).
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


class AiHelperCell(Base):
    __tablename__ = "ai_helper_cells"
    __table_args__ = (
        UniqueConstraint("run_id", "row_id", "column_id", name="uq_ahc_run_row_col"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("ai_helper_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Plain ints (no FK): a later row/column delete shouldn't cascade away the
    # historical run + its revert snapshot.
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # pending → done | failed | skipped (re-query pending = idempotent).
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    # Target cell's pre-write value (revert) + the value written.
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
