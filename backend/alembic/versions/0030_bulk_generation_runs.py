"""bulk_generation_runs + cells.generation_run_id — make bulk AI cell
generation cancellable and observable.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-27

Why this exists:
``POST /library/tables/{id}/generate`` used to fan a Celery task per cell
and return — no run-level tracking, no way to cancel a runaway batch
mid-flight, no aggregate progress. Workers ran until the queue drained.
Mirrors the bulk_publish_runs pattern so the editor UI can show a
progress banner with a Cancel button.

Schema mirrors ``bulk_publish_runs`` deliberately so the frontend
patterns and operator mental model line up across the two surfaces:
  * status: queued | running | cancelled | done | failed
  * total / done / failed / skipped counters
  * started_at / finished_at timestamps for clean elapsed-time reporting

`bulk_table_cells.generation_run_id` is the cell→run back-link. It's
nullable so cells generated before this migration (or via the legacy
inline-edit path) don't break — the column simply stays NULL for them.
ON DELETE SET NULL because a finished/cancelled run can eventually be
hard-deleted without taking its cell history with it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulk_generation_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # queued → running → (cancelled | done | failed). The set is
        # closed on purpose; the worker rejects unknown values.
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bulk_generation_runs_table_id",
        "bulk_generation_runs",
        ["table_id"],
    )
    op.create_index(
        "ix_bulk_generation_runs_status",
        "bulk_generation_runs",
        ["status"],
    )
    # Lets the "active run for this table" lookup go straight to the
    # index instead of scanning, since the operator only ever has 0..1
    # active runs per table.
    op.create_index(
        "ix_bulk_generation_runs_table_status_created",
        "bulk_generation_runs",
        ["table_id", "status", sa.text("created_at DESC")],
    )

    op.add_column(
        "bulk_table_cells",
        sa.Column(
            "generation_run_id",
            sa.BigInteger,
            sa.ForeignKey("bulk_generation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bulk_table_cells_generation_run_id",
        "bulk_table_cells",
        ["generation_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bulk_table_cells_generation_run_id", table_name="bulk_table_cells"
    )
    op.drop_column("bulk_table_cells", "generation_run_id")
    op.drop_index(
        "ix_bulk_generation_runs_table_status_created",
        table_name="bulk_generation_runs",
    )
    op.drop_index(
        "ix_bulk_generation_runs_status", table_name="bulk_generation_runs"
    )
    op.drop_index(
        "ix_bulk_generation_runs_table_id", table_name="bulk_generation_runs"
    )
    op.drop_table("bulk_generation_runs")
