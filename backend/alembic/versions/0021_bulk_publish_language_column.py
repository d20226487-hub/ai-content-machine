"""Bulk publish — per-row language column for multi-site runs.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-12

Adds ``language_column_id`` (FK → bulk_table_columns, SET NULL) to both
``bulk_publish_runs`` and ``bulk_table_publish_mappings``.

In multi mode, when this column is set, each row's language is read from
the matching cell instead of using the run-level language. The cell value
is lowercased + trimmed, then matched against the resolved domain's
``languages[]`` list. Empty cells fail the row (strict mode — if you
turn on the per-row language column, every row must have a language
value). Cells with a language not configured on the resolved domain
also fail the row with a clear message.

Single-mode runs ignore this column — single-mode is always run-level
language by definition (one domain, one language).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_publish_runs",
        sa.Column("language_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_publish_runs_language_column_id",
        "bulk_publish_runs",
        "bulk_table_columns",
        ["language_column_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column("language_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_table_publish_mappings_language_column_id",
        "bulk_table_publish_mappings",
        "bulk_table_columns",
        ["language_column_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_bulk_table_publish_mappings_language_column_id",
        "bulk_table_publish_mappings",
        type_="foreignkey",
    )
    op.drop_column("bulk_table_publish_mappings", "language_column_id")

    op.drop_constraint(
        "fk_bulk_publish_runs_language_column_id",
        "bulk_publish_runs",
        type_="foreignkey",
    )
    op.drop_column("bulk_publish_runs", "language_column_id")
