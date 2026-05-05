"""domains table for the Publish section

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("cms_type", sa.String(length=30), nullable=False),
        sa.Column("auth_type", sa.String(length=30), nullable=False),
        sa.Column(
            "credentials_encrypted", sa.Text(), nullable=True,
        ),
        sa.Column(
            "languages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "multilingual_plugin",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
        sa.Column(
            "custom_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
            onupdate=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_domains_cms_type", "domains", ["cms_type"])
    op.create_index("ix_domains_created_by_id", "domains", ["created_by_id"])
    op.create_unique_constraint("uq_domains_base_url", "domains", ["base_url"])


def downgrade() -> None:
    op.drop_constraint("uq_domains_base_url", "domains", type_="unique")
    op.drop_index("ix_domains_created_by_id", table_name="domains")
    op.drop_index("ix_domains_cms_type", table_name="domains")
    op.drop_table("domains")
