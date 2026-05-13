"""Bulk publish — Update mode (create-or-update).

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-12

Adds three columns to `bulk_publish_runs` and matching ones on
`bulk_table_publish_mappings`:

  operation        'create' | 'update'  (default 'create' — runs that
                                         predate this migration keep
                                         their old behavior)
  lookup_kind      'id' | 'slug' | NULL  (set only when operation='update')
  lookup_column_id INT NULL              (FK → bulk_table_columns;
                                          SET NULL on cascade)

For Update runs the worker reads each row's lookup value from
``lookup_column_id``, resolves it to a WordPress post_id (by id or by
slug per ``lookup_kind``), and PATCHes that post with the configured
field_to_column mapping. Empty cells are omitted from the PATCH body so
WP leaves those fields unchanged (matches the spreadsheet "blank = don't
touch" mental model).

Custom-CMS publishing in Update mode is rejected at run creation time
(WP-only for v1; Custom CMS has no PATCH/find convention). Multi-mode
Update works the same as multi-mode Create — per-row resolution still
chooses the domain, the operation is run-wide.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- bulk_publish_runs ----
    op.add_column(
        "bulk_publish_runs",
        sa.Column(
            "operation",
            sa.String(16),
            nullable=False,
            server_default="create",
        ),
    )
    op.add_column(
        "bulk_publish_runs",
        sa.Column("lookup_kind", sa.String(16), nullable=True),
    )
    op.add_column(
        "bulk_publish_runs",
        sa.Column("lookup_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_publish_runs_lookup_column_id",
        "bulk_publish_runs",
        "bulk_table_columns",
        ["lookup_column_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- bulk_table_publish_mappings ----
    # Mirror the new fields so saved mappings carry the operation + lookup
    # config across modal opens (single + multi).
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column(
            "operation",
            sa.String(16),
            nullable=False,
            server_default="create",
        ),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column("lookup_kind", sa.String(16), nullable=True),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column("lookup_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_table_publish_mappings_lookup_column_id",
        "bulk_table_publish_mappings",
        "bulk_table_columns",
        ["lookup_column_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_bulk_table_publish_mappings_lookup_column_id",
        "bulk_table_publish_mappings",
        type_="foreignkey",
    )
    op.drop_column("bulk_table_publish_mappings", "lookup_column_id")
    op.drop_column("bulk_table_publish_mappings", "lookup_kind")
    op.drop_column("bulk_table_publish_mappings", "operation")

    op.drop_constraint(
        "fk_bulk_publish_runs_lookup_column_id",
        "bulk_publish_runs",
        type_="foreignkey",
    )
    op.drop_column("bulk_publish_runs", "lookup_column_id")
    op.drop_column("bulk_publish_runs", "lookup_kind")
    op.drop_column("bulk_publish_runs", "operation")
