"""gdocs importer: per-row slug audit (anchor → final slug).

Revision ID: 0051
Revises: 0050
Create Date: 2026-06-04

Stores, for each row a Google-Docs import built, what the AI pairing did to its
slug: the raw link anchor the writer attached (the "before") and the final slug
taken from Structure (the "after"), plus row/lang/seo-title for review. Drives
the "AI slug mapping" audit panel on the table page so the operator can check
and track the pairing. NULL for tables not built by the importer.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_tables",
        sa.Column("gdocs_slug_audit", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_tables", "gdocs_slug_audit")
