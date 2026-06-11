"""normalize_runs — revertable bulk normalize history per table.

Revision ID: 0053
Revises: 0052
Create Date: 2026-06-11

Why this exists:
The bulk-table editor gained a Normalize content tool (trim whitespace, strip
URL scheme, strip edge slashes, lowercase). It applies the selected transforms
across every cell in the chosen columns at once, so — like Find & Replace — it
needs a safety net: each run stores a full before/after ``snapshot`` and is
revertable in one click (revert re-writes the old values back through the normal
cell path).

Mirrors ``find_replace_runs`` (migration 0033) exactly, except the
find/replace-specific columns (pattern, replacement, is_regex, case_sensitive,
whole_cell, match_count) are replaced by a single ``operations`` JSONB list of
the selected transforms in canonical order.

History is persistent — runs live until their table is hard-deleted
(ON DELETE CASCADE).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "normalize_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "operations",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "column_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("cell_count", sa.Integer, nullable=False, server_default="0"),
        # 'applied' | 'reverted'
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="applied",
        ),
        sa.Column("name", sa.String(length=200), nullable=True),
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
        "ix_normalize_runs_table_created",
        "normalize_runs",
        ["table_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_normalize_runs_table_created", table_name="normalize_runs"
    )
    op.drop_table("normalize_runs")
