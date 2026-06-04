"""Add link-type classification to crawl/juxtapose link-check runs.

Revision ID: 0047
Revises: 0046
Create Date: 2026-06-04

The Status-Code (crawl) and juxtapose methods can now classify each link as
product / internal / external — the same buckets the translation mode uses —
so the run page can filter by link type.

``link_check_runs.classify_config`` holds the run's domain config
(``{"product_domains": [str], "internal_domain_column_ids": [int]}``); NULL =
no classification requested (the link-type filter is hidden for that run).
``link_check_violations.link_type`` stores each finding's bucket, computed at
seed time so the filter is a plain indexed SQL predicate.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_check_runs",
        sa.Column("classify_config", JSONB(), nullable=True),
    )
    op.add_column(
        "link_check_violations",
        sa.Column("link_type", sa.String(length=12), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("link_check_violations", "link_type")
    op.drop_column("link_check_runs", "classify_config")
