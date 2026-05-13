"""prompts.deleted_at — Trash for prompts.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-12

Mirrors the bulk_tables / domains Trash pattern. Adds a nullable
``deleted_at`` timestamp + partial index on ``deleted_at IS NOT NULL``.

Prompts protected by Trash for the same reason as the others: deleting
a prompt today is irreversible and loses the entire immutable version
history. The bulk-table cells / saved generations that snapshot the
prompt text keep working (they store the rendered text, not a live
reference), but you can never re-run generation against the deleted
prompt's slot. Trash gives a window to undo.

Visibility: same per-role rules as the active list — admin/manager see
all, content_generator sees their own. ``bulk_table_columns.prompt_id``
already has ``ON DELETE SET NULL`` so permanent-delete leaves a clean
"no prompt" marker on cells that referenced it.

Auto-empty: ``app_settings.prompt_trash_retention_days`` (default 50,
0 disables). Cleanup runs in the shared daily ``trash.cleanup`` task.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_prompts_deleted_at",
        "prompts",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompts_deleted_at",
        table_name="prompts",
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.drop_column("prompts", "deleted_at")
