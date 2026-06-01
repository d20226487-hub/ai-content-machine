"""structure_format_runs — revertable bulk structure/formatting history.

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-01

The bulk-table editor gains a 3rd content tool, "Structure & Formatting":
a user-selected subset of deterministic transforms (markdown->HTML, strip
response-start junk, strip inline CSS, strip bold/italic/underline) applied
across the chosen columns in a fixed order. Like find_replace_runs it is
applied at once and stores a full before/after ``snapshot`` so the whole run
reverts in one click. History is persistent (CASCADE on table delete).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "structure_format_runs",
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
    op.create_index(
        "ix_structure_format_runs_table_created",
        "structure_format_runs",
        ["table_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_structure_format_runs_table_created",
        table_name="structure_format_runs",
    )
    op.drop_table("structure_format_runs")
