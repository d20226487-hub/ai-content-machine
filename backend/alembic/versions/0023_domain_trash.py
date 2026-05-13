"""domains.deleted_at — Trash for domains.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-12

Mirrors the bulk_tables Trash pattern (migration 0019): adds a nullable
``deleted_at`` timestamp + partial index for the trash listing query.
NULL = active, non-NULL = trashed.

All publish surfaces (single + bulk) filter ``deleted_at IS NULL``, so a
trashed domain can't be picked as a publish target. Existing
``publish_jobs`` rows keep their FK and continue to render under the
domain's original name (we never lose the row, only hide it). Trash is
blocked when an in-flight bulk publish run is using this domain — same
posture as bulk_tables.

Auto-empty via the daily ``trash.cleanup`` Celery task; retention
configured at ``app_settings.domain_trash_retention_days`` (default 50,
0 disables).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "domains",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_domains_deleted_at",
        "domains",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )

    # The original UNIQUE(name) + UNIQUE(base_url) constraints span ALL
    # rows including trashed ones, which would block a user from creating
    # a new "Site A" while an old "Site A" is sitting in trash. Convert
    # both to partial-unique indexes that only fire for active rows.
    # Trashed rows can carry "stale" duplicates of names/urls held by new
    # active rows — that's fine because they're invisible to every active
    # surface. On restore, we re-check uniqueness against the active set
    # in the application layer.
    op.drop_constraint("uq_domains_name", "domains", type_="unique")
    op.drop_constraint("uq_domains_base_url", "domains", type_="unique")
    op.create_index(
        "uq_domains_name_active",
        "domains",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_domains_base_url_active",
        "domains",
        ["base_url"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_domains_base_url_active", table_name="domains")
    op.drop_index("uq_domains_name_active", table_name="domains")
    op.create_unique_constraint("uq_domains_base_url", "domains", ["base_url"])
    op.create_unique_constraint("uq_domains_name", "domains", ["name"])

    op.drop_index(
        "ix_domains_deleted_at",
        table_name="domains",
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.drop_column("domains", "deleted_at")
