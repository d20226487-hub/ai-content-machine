"""Add per-job prompt to link_fix_runs.

Revision ID: 0045
Revises: 0044
Create Date: 2026-06-03

The AI link-fix step now lets the user specify the correction prompt per job
(instead of only the global Brain ``fix_links`` prompt). Each fix run records
the prompt it used, which also lets the UI default the next job to the
previously-used prompt. NULL = the run used the Brain default.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_fix_runs",
        sa.Column("prompt", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("link_fix_runs", "prompt")
