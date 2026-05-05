"""Add profile_name + warnings to publish_jobs.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publish_jobs",
        sa.Column("profile_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "publish_jobs",
        sa.Column(
            "warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("publish_jobs", "warnings")
    op.drop_column("publish_jobs", "profile_name")
