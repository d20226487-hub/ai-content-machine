"""AI Helper mini-tool: revertable per-cell AI runs over a bulk table.

Revision ID: 0069
Revises: 0068
Create Date: 2026-07-24

A general bulk-table tool: the operator gives a prompt (typed or from the
library) + maps ``{{columns}}``, picks Read (write to a target column) or Edit
(rewrite in place), and every selected row gets one AI call, distributed as a
revertable run — mirroring the link-fix / bulk-generation run shape so the UI
reuses the same polling/progress/revert machinery.

  * ``ai_helper_runs`` — lifecycle + counters + the run config (mode, prompt,
    variable_map, target column, provider/model, input word-slice, row scope)
    + revert stamp.
  * ``ai_helper_cells`` — one row per (row, target column) processed; the unit
    of distributed work AND the before/after snapshot for revert.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0069"
down_revision: Union[str, None] = "0068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_helper_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # queued → running → (cancelled | done | failed)
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="queued"
        ),
        # 'read' (write to a target output column) | 'edit' (rewrite in place)
        sa.Column(
            "mode", sa.String(length=8), nullable=False, server_default="read"
        ),
        # Optional label (NULL → UI "<tool> #<id>" fallback).
        sa.Column("name", sa.String(length=200), nullable=True),
        # The task prompt, snapshotted (contains {{var}} placeholders).
        sa.Column("prompt", sa.Text, nullable=False),
        # Provenance if loaded from the library (SET NULL so deleting the prompt
        # keeps the run's snapshot intact).
        sa.Column(
            "prompt_id",
            sa.Integer,
            sa.ForeignKey("prompts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # {var_name: source_column_id} — the input columns the prompt reads.
        sa.Column(
            "variable_map", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        # Read: the column the output is written to. Edit: the column rewritten.
        sa.Column(
            "target_column_id",
            sa.Integer,
            sa.ForeignKey("bulk_table_columns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Per-run AI config (NULL = fall back to first-enabled provider + default).
        sa.Column("provider_code", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("max_output_tokens", sa.Integer, nullable=True),
        # Input word-slice: 'full' | 'first_pct'. When 'first_pct', only the
        # first `input_pct`% of `slice_column_id`'s words (rounded to an HTML
        # block boundary) is sent; in Edit mode the AI's reply is spliced back
        # onto the untouched remainder.
        sa.Column(
            "input_scope", sa.String(length=12), nullable=False, server_default="full"
        ),
        sa.Column("input_pct", sa.Integer, nullable=True),
        sa.Column("slice_column_id", sa.Integer, nullable=True),
        # Snapshot of the rows this run targets (selection / range / filter).
        sa.Column(
            "row_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        # NULL = applied; set when the run's writes were reverted (edit mode).
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_helper_runs_status", "ai_helper_runs", ["status"])

    op.create_table(
        "ai_helper_cells",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("ai_helper_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Plain ints (no FK): a later row/column delete shouldn't cascade away
        # the historical run + its revert snapshot.
        sa.Column("row_id", sa.Integer, nullable=False),
        sa.Column("row_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("column_id", sa.Integer, nullable=False),
        # pending → done | failed | skipped (re-query pending = idempotent).
        sa.Column(
            "state", sa.String(length=12), nullable=False, server_default="pending"
        ),
        # Target cell's pre-write value (revert) + the value written.
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.UniqueConstraint("run_id", "row_id", "column_id", name="uq_ahc_run_row_col"),
    )
    op.create_index("ix_ahc_run_state", "ai_helper_cells", ["run_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_ahc_run_state", table_name="ai_helper_cells")
    op.drop_table("ai_helper_cells")
    op.drop_index("ix_ai_helper_runs_status", table_name="ai_helper_runs")
    op.drop_table("ai_helper_runs")
