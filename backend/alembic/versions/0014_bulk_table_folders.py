"""Bulk-table folders (flat, no nesting).

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-04

Adds simple top-level folders to organize bulk tables. The schema is
deliberately flat — no parent_id column — because the UX explicitly does not
need subfolders right now. Adding nesting later means an additional column +
migration; the rest of the API stays compatible.

Tables drop their folder via `bulk_tables.folder_id IS NULL` (= "uncategorized").
ON DELETE RESTRICT on the FK so deleting a folder fails when it still has
tables — the API surfaces a clean "move tables out first" error instead of
silently orphaning them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulk_table_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "bulk_tables",
        sa.Column(
            "folder_id",
            sa.Integer(),
            sa.ForeignKey("bulk_table_folders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bulk_tables_folder_id", "bulk_tables", ["folder_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_tables_folder_id", table_name="bulk_tables")
    op.drop_column("bulk_tables", "folder_id")
    op.drop_table("bulk_table_folders")
