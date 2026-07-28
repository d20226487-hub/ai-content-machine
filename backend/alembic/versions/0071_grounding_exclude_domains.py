"""Per-column grounding blacklist: bulk_table_columns.grounding_exclude_domains.

Grounding with Google Search has no allowlist, but the Vertex ``googleSearch``
tool accepts ``excludeDomains`` — a blacklist. Store it per column (a list of
bare hostnames) alongside the existing ``grounding`` flag; NULL/[] = no
exclusions. Only meaningful when ``grounding`` is set.

Revision ID: 0071
Revises: 0070
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0071"
down_revision: Union[str, None] = "0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_columns",
        sa.Column("grounding_exclude_domains", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_columns", "grounding_exclude_domains")
