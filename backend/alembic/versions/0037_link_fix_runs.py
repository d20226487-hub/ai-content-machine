"""link checker: AI link-fix runs (revertable) + scoped re-check.

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-31

The Link Checker gains an AI "fix" pass. After a check run, the user picks
rows (or all) and an LLM rewrites ONLY the links in the flagged output
cells per the Brain ``fix_links`` prompt (integrate a missing expected
link, correct a typo'd one, remove a hallucinated one). The work is a
revertable run with before/after snapshots, mirroring Find & Replace.

  * ``link_fix_runs`` — lifecycle + counters + revert stamp; ``source_run_id``
    is the check run it was launched from; ``recheck_run_id`` is the scoped
    LinkCheckRun auto-created when the fix finishes so the user sees residual
    problems.
  * ``link_fix_cells`` — one row per (row, output column) being fixed, the
    unit of distributed work AND the before/after snapshot for revert.
  * ``link_check_runs.row_ids`` — optional row scope (NULL = all rows). The
    auto re-check uses it to crawl/juxtapose only the cells that were fixed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Optional row scope for a check run (NULL = all rows). Used by the
    # auto re-check to re-scan only the rows a fix run touched.
    op.add_column(
        "link_check_runs",
        sa.Column("row_ids", JSONB, nullable=True),
    )

    op.create_table(
        "link_fix_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # The check run this fix was launched from. SET NULL so a deleted /
        # purged check run doesn't take the fix history with it.
        sa.Column(
            "source_run_id",
            sa.BigInteger,
            sa.ForeignKey("link_check_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The scoped LinkCheckRun auto-created on finish (residual problems).
        sa.Column(
            "recheck_run_id",
            sa.BigInteger,
            sa.ForeignKey("link_check_runs.id", ondelete="SET NULL"),
            nullable=True,
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
        # Snapshot of the source run's column config so the worker + re-check
        # don't depend on the (mutable) check run still existing.
        sa.Column(
            "column_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "expected_column_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        # NULL = applied; set when the run's writes were rolled back.
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

    op.create_table(
        "link_fix_cells",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("link_fix_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Plain ints (no FK): a later row/column delete shouldn't cascade away
        # the historical fix. column_name snapshot keeps the row renderable.
        sa.Column("row_id", sa.Integer, nullable=False),
        sa.Column("row_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("column_id", sa.Integer, nullable=False),
        sa.Column("column_name", sa.String(length=120), nullable=False),
        # pending → done | failed | skipped (re-query pending = idempotent).
        sa.Column(
            "state", sa.String(length=12), nullable=False, server_default="pending"
        ),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        # The flagged links fed to the AI: [{problem, link, detail_code, status_code}]
        sa.Column(
            "violations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.UniqueConstraint("run_id", "row_id", "column_id", name="uq_lfc_run_row_col"),
    )
    op.create_index(
        "ix_lfc_run_state", "link_fix_cells", ["run_id", "state"]
    )


def downgrade() -> None:
    op.drop_index("ix_lfc_run_state", table_name="link_fix_cells")
    op.drop_table("link_fix_cells")
    op.drop_table("link_fix_runs")
    op.drop_column("link_check_runs", "row_ids")
