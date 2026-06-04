"""Add link_check_dismissals (dismissed translation-table errors).

Revision ID: 0046
Revises: 0045
Create Date: 2026-06-04

The translation raw-table view lets the user bulk-dismiss wrong/made-up links
they've reviewed. A dismissal is a (run, row, link) tuple; the view recomputes
on demand and hides dismissed errors from the active discrepancy filter (they
remain visible — and restorable — under the "dismissed" view).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "link_check_dismissals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("link_check_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Plain int (no FK) so a later row delete doesn't matter — a stale
        # dismissal simply never matches.
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id", "row_id", "link", name="uq_lc_dismissal_run_row_link"
        ),
    )


def downgrade() -> None:
    op.drop_table("link_check_dismissals")
