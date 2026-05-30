"""find_replace_runs — revertable bulk find-and-replace history per table.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-30

Why this exists:
The bulk-table editor gained a find/replace content tool. Plain *Find* is
read-only and persists nothing. *Replace* applies across every matching
cell at once, so it needs a safety net: each replace stores a full
before/after ``snapshot`` and is revertable in one click (revert re-writes
the old values back through the normal cell path).

History is persistent — runs live until their table is hard-deleted
(ON DELETE CASCADE), mirroring how gen-runs / publish-runs are kept.
The ``snapshot`` JSONB holds ``[{row_id, column_id, old_value, old_status,
new_value}]`` and drives both the before/after table on the run page and
the revert itself.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "find_replace_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern", sa.Text, nullable=False),
        sa.Column("replacement", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "is_regex", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "case_sensitive",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "whole_cell", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "column_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("match_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cell_count", sa.Integer, nullable=False, server_default="0"),
        # 'applied' | 'reverted'
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="applied",
        ),
        sa.Column(
            "snapshot",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The history list for a table reads newest-first; this index serves it
    # without a sort.
    op.create_index(
        "ix_find_replace_runs_table_created",
        "find_replace_runs",
        ["table_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_find_replace_runs_table_created", table_name="find_replace_runs"
    )
    op.drop_table("find_replace_runs")
