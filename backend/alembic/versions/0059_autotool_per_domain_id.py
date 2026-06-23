"""Per-domain Autotool id: move external_id from the run to the item.

Revision ID: 0059
Revises: 0058
Create Date: 2026-06-23

The proxy assigns one id per SITE (not per run): each domain's first request
grabs its own id, which its remaining requests carry. So the captured id lives
on the item now — set on every item of a domain once that domain's leader
captures it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autotool_run_items",
        sa.Column("external_id", JSONB(), nullable=True),
    )
    op.drop_column("autotool_runs", "external_id")


def downgrade() -> None:
    op.add_column(
        "autotool_runs",
        sa.Column("external_id", JSONB(), nullable=True),
    )
    op.drop_column("autotool_run_items", "external_id")
