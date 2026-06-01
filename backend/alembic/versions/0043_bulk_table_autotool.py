"""Add autotool fields to bulk_tables (public CSV proxy export).

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-01

Autotool is a publishing mode where an external proxy ("Autotool") fetches a
table's CSV over plain HTTP and pushes it to WordPress / target sites. To let
it read the data without a login we expose the table as a CSV at an
unguessable, unauthenticated URL.

Two columns drive it:
  * autotool_enabled — whether the table is currently exposed.
  * autotool_token   — random per-table token that forms the public URL
                       (/autotool/<token>.csv). Nullable + UNIQUE: cleared on
                       disable so the old link is permanently dead, and a fresh
                       token is minted on the next enable.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_tables",
        sa.Column(
            "autotool_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "bulk_tables",
        sa.Column("autotool_token", sa.String(length=36), nullable=True),
    )
    # UNIQUE so a token maps to at most one table; partial-friendly because
    # Postgres allows many NULLs under a UNIQUE index (disabled tables hold
    # NULL). Name matches SQLAlchemy's default ix_%(table)s_%(column)s so the
    # ORM metadata and the DB agree.
    op.create_index(
        "ix_bulk_tables_autotool_token",
        "bulk_tables",
        ["autotool_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_tables_autotool_token", table_name="bulk_tables")
    op.drop_column("bulk_tables", "autotool_token")
    op.drop_column("bulk_tables", "autotool_enabled")
