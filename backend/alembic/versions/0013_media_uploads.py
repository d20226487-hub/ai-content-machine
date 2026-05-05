"""media_uploads cache: per-(domain, source_url) → wp_media_id.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-03

Avoids re-uploading the same image to the same WordPress site twice when a
bulk run has many rows referencing the same hero image. The cache is
deliberately simple: composite primary key (domain_id, source_url), no TTL
in v1. If a cached id stops working (media deleted on the WP side), the
publish surfaces a warning and the user can clear the cache.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_uploads",
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_url", sa.String(length=2000), primary_key=True),
        sa.Column("wp_media_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_media_uploads_domain_id", "media_uploads", ["domain_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_media_uploads_domain_id", table_name="media_uploads")
    op.drop_table("media_uploads")
