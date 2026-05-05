"""Add publish_config jsonb on domains; create publish_jobs table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "domains",
        sa.Column(
            "publish_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column(
            "source_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column(
            "payload_sent",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "response_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("cms_post_id", sa.String(length=200), nullable=True),
        sa.Column("cms_post_url", sa.String(length=1000), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_publish_jobs_created_at_desc",
        "publish_jobs",
        [sa.text("created_at DESC")],
    )
    op.create_index("ix_publish_jobs_domain_id", "publish_jobs", ["domain_id"])
    op.create_index("ix_publish_jobs_status", "publish_jobs", ["status"])
    op.create_index(
        "ix_publish_jobs_created_by_id", "publish_jobs", ["created_by_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_publish_jobs_created_by_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_status", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_domain_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_created_at_desc", table_name="publish_jobs")
    op.drop_table("publish_jobs")
    op.drop_column("domains", "publish_config")
