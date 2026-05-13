"""bulk_tables.deleted_at — soft-delete + trash page.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-12

Adds a `deleted_at` timestamp to `bulk_tables`. NULL = active, non-NULL =
trashed. All existing list/get endpoints filter `deleted_at IS NULL`; a
new `/library/trash*` surface lists, previews, restores, and permanently
deletes trashed rows. An optional auto-empty cleanup (Celery beat task)
deletes rows older than `app_settings.bulk_table_trash_retention_days`
(default 50 — configurable; 0 disables).

A partial index on the `deleted_at IS NOT NULL` predicate keeps the trash
listing query fast even on tables with many never-deleted rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_tables",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index: only trashed rows. Cheap, doesn't bloat the table.
    op.create_index(
        "ix_bulk_tables_deleted_at",
        "bulk_tables",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bulk_tables_deleted_at",
        table_name="bulk_tables",
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.drop_column("bulk_tables", "deleted_at")
