"""Run names (all tools) + link-fix target column.

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-31

  * ``name`` (nullable) on every run table — find_replace / link_check /
    link_fix / bulk_generation / bulk_publish — so users can rename a run.
    When NULL the UI falls back to a "<tool> #<id>" label.
  * ``link_fix_runs.target_column_id`` — the column corrected content is
    written to (lets the original output column be preserved). NULL = write
    back to the source column (overwrite).
  * ``link_fix_cells.source_value`` — the original source content, kept for
    the before/after display independently of the target cell's prior value
    (which ``old_value`` snapshots for revert).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RUN_TABLES = (
    "find_replace_runs",
    "link_check_runs",
    "link_fix_runs",
    "bulk_generation_runs",
    "bulk_publish_runs",
)


def upgrade() -> None:
    for tbl in _RUN_TABLES:
        op.add_column(tbl, sa.Column("name", sa.String(length=200), nullable=True))

    op.add_column(
        "link_fix_runs",
        sa.Column(
            "target_column_id",
            sa.Integer,
            sa.ForeignKey("bulk_table_columns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "link_fix_cells",
        sa.Column("source_value", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("link_fix_cells", "source_value")
    op.drop_column("link_fix_runs", "target_column_id")
    for tbl in _RUN_TABLES:
        op.drop_column(tbl, "name")
