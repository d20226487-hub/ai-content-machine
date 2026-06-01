"""Structure & Formatting → background job model (progress + per-cell rows).

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-01

The synchronous apply doesn't scale to large tables (5k+ rows): the request
can hit the proxy timeout and the revert ``snapshot`` JSONB balloons to
hundreds of MB when most cells change. This moves the tool to the same
background-job shape as the Link Checker:

  * ``structure_format_runs`` gains a processing lifecycle
    (queued|running|done|failed|cancelled) + progress counters + stamps.
  * A new ``structure_format_cells`` table holds one row per CANDIDATE cell
    (state pending|done|skipped|failed). Only ``done`` rows carry the
    before/after values — paginated via SQL on the run page, and the source
    of truth for revert. This replaces the single ``snapshot`` blob.

DATA-PRESERVING: an existing applied run is real user data. We expand its
``snapshot`` into ``structure_format_cells`` (state ``done``) and mark the run
``done`` BEFORE dropping the blob, so its one-click revert keeps working.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- run table: lifecycle + progress + stamps ---
    op.add_column(
        "structure_format_runs",
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column("done", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column(
            "last_progress_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "structure_format_runs",
        sa.Column("error", sa.Text, nullable=True),
    )
    # New runs start 'queued' now (was 'applied').
    op.alter_column(
        "structure_format_runs", "status", server_default="queued"
    )

    # --- per-cell table (unit of work + before/after snapshot) ---
    op.create_table(
        "structure_format_cells",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("structure_format_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("row_id", sa.Integer, nullable=False),
        sa.Column("row_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("column_id", sa.Integer, nullable=False),
        sa.Column("column_name", sa.String(length=120), nullable=False),
        # pending → done | skipped | failed
        sa.Column(
            "state", sa.String(length=12), nullable=False, server_default="pending"
        ),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("old_status", sa.String(length=16), nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.UniqueConstraint(
            "run_id", "row_id", "column_id", name="uq_sfc_run_row_col"
        ),
    )
    op.create_index(
        "ix_sfc_run_state", "structure_format_cells", ["run_id", "state"]
    )

    # --- migrate existing snapshots into the per-cell table (data-preserving) ---
    op.execute(
        """
        INSERT INTO structure_format_cells
            (run_id, row_id, row_position, column_id, column_name, state,
             old_value, old_status, new_value)
        SELECT r.id,
               (e->>'row_id')::int,
               COALESCE(rw.position, 0),
               (e->>'column_id')::int,
               COALESCE(col.name, '—'),
               'done',
               e->>'old_value',
               e->>'old_status',
               e->>'new_value'
        FROM structure_format_runs r
        CROSS JOIN LATERAL jsonb_array_elements(r.snapshot) e
        LEFT JOIN bulk_table_rows rw ON rw.id = (e->>'row_id')::int
        LEFT JOIN bulk_table_columns col ON col.id = (e->>'column_id')::int
        """
    )
    # Existing runs are all terminal — map to the new 'done' lifecycle and
    # backfill progress so the run page renders consistently. reverted_at
    # already distinguishes reverted runs.
    op.execute(
        """
        UPDATE structure_format_runs
        SET status = 'done',
            total = cell_count,
            done = cell_count,
            started_at = created_at,
            finished_at = created_at
        """
    )

    op.drop_column("structure_format_runs", "snapshot")


def downgrade() -> None:
    op.add_column(
        "structure_format_runs",
        sa.Column(
            "snapshot",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE structure_format_runs r
        SET snapshot = COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                'row_id', c.row_id,
                'column_id', c.column_id,
                'old_value', c.old_value,
                'old_status', c.old_status,
                'new_value', c.new_value
            ))
            FROM structure_format_cells c
            WHERE c.run_id = r.id AND c.state = 'done'
        ), '[]'::jsonb)
        """
    )
    op.execute(
        "UPDATE structure_format_runs SET status = "
        "CASE WHEN reverted_at IS NULL THEN 'applied' ELSE 'reverted' END"
    )
    op.alter_column(
        "structure_format_runs", "status", server_default="applied"
    )
    op.drop_index("ix_sfc_run_state", table_name="structure_format_cells")
    op.drop_table("structure_format_cells")
    for col in (
        "error",
        "last_progress_at",
        "finished_at",
        "started_at",
        "failed",
        "done",
        "total",
    ):
        op.drop_column("structure_format_runs", col)
