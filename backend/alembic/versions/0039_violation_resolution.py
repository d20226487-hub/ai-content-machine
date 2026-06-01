"""Per-violation resolution stamp for the in-place AI re-verify.

Revision ID: 0039
Revises: 0038
Create Date: 2026-06-01

After an AI link-fix run finishes, instead of spawning a separate re-check
job we re-juxtapose the corrected cells in place and stamp each affected
violation on the ORIGINAL check run:

  * NULL       — untouched: no applied fix processed this violation's cell.
  * 'solved'   — the cell was fixed and this problem is gone on re-juxtapose.
  * 'unsolved' — the cell was fixed but this problem is still present.

Reverting a fix run clears the stamps it set back to NULL (untouched).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_check_violations",
        sa.Column("resolution", sa.String(length=12), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("link_check_violations", "resolution")
