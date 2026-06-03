"""Add translation_config to link_check_runs (3rd mode: translation links).

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-03

The Link Checker gains a 3rd mode — "Check Translation Links". Unlike the
crawl / juxtapose modes it doesn't read expected links from a column; it
COMPUTES them by localizing each original link (inserting the row's language
as a subfolder) under a per-type treatment (product / internal / external),
then juxtaposes the translation's actual links against those computed
expected links.

The whole mode config (column roles, internal domains, product rules,
treatments, per-language exceptions) is stored in one nullable JSONB blob.
NULL = a classic crawl/juxtapose run; non-NULL = a translation run. Keeping
it in a single column avoids a wide migration and lets the shape evolve
without further DDL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_check_runs",
        sa.Column("translation_config", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("link_check_runs", "translation_config")
