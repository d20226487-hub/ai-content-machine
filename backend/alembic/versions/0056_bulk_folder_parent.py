"""bulk_table_folders.parent_id — nested Library folders (subfolders).

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-19

Library folders were flat (no nesting); the "New folder" button worked inside a
folder but the created folder had nowhere to attach, so it surfaced at the root.
This adds a self-referencing ``parent_id`` (null = top level) so folders can
nest — same shape as ``domain_folders`` (migration 0027). ON DELETE RESTRICT +
the API-layer empty-folder check keep a non-empty folder from being deleted out
from under its children.

Backfill-free: every existing folder gets ``parent_id = NULL`` (stays at the
root), so nothing moves.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_folders",
        sa.Column("parent_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_table_folders_parent",
        "bulk_table_folders",
        "bulk_table_folders",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_bulk_table_folders_parent_id",
        "bulk_table_folders",
        ["parent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bulk_table_folders_parent_id", table_name="bulk_table_folders"
    )
    op.drop_constraint(
        "fk_bulk_table_folders_parent", "bulk_table_folders", type_="foreignkey"
    )
    op.drop_column("bulk_table_folders", "parent_id")
