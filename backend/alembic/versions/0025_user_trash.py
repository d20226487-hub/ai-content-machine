"""users.deleted_at — Trash for users.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-12

Mirrors the prior Trash migrations (0019 bulk_tables, 0023 domains,
0024 prompts).

Key wrinkle vs the others: ``users.email`` is currently UNIQUE across
ALL rows. With Trash that would block creating a new active user with
an email that's sitting in trash. We convert it to a partial-unique
index that fires only for active rows — trashed users can hold
"stale" emails. Restore re-checks uniqueness against the active set
in the application layer (clean 409 instead of an IntegrityError).

Auto-empty via the shared daily ``trash.cleanup`` task; retention
``app_settings.user_trash_retention_days`` (default 50, 0 disables).
The cleanup task uses the same active-admin guard as the API
endpoints so a trashed last-admin can never be silently auto-purged.

Hot-session impact: ``get_current_user`` (deps.py) also filters
``deleted_at IS NULL`` after this migration, so the JWT of a trashed
user is rejected on the very next request. Matches the old
hard-delete behavior — no surprise lingering sessions.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_deleted_at",
        "users",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )

    # Flip UNIQUE(email) to partial-unique-on-active.
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_index(
        "uq_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_active", table_name="users")
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.drop_index(
        "ix_users_deleted_at",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.drop_column("users", "deleted_at")
