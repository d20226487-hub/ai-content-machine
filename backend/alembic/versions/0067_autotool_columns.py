"""Per-table Autotool column selection.

Revision ID: 0067
Revises: 0066
Create Date: 2026-07-23

Adds ``bulk_tables.autotool_column_ids`` — a JSONB list of column ids to include
in the table's Autotool CSV (both the public ``/autotool/<token>.csv`` link and
the per-domain send files, which are served by the same builder). NULL = every
column, so tables exposed before this migration are unchanged. Lets an operator
drop helper/internal columns from what Autotool sees without deleting them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0067"
down_revision: Union[str, None] = "0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_tables",
        sa.Column("autotool_column_ids", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_tables", "autotool_column_ids")
