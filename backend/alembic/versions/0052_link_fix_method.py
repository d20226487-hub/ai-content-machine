"""Add a method discriminator to link_fix_runs.

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-05

The Link Checker now has two kinds of correction job that share the
``link_fix_runs`` / ``link_fix_cells`` machinery (snapshots, revert,
re-verify, history list):

  * ``ai``      — an LLM rewrites the links in each flagged cell (the
                  original behavior).
  * ``replace`` — a deterministic swap of each wrong translation link for
                  its computed expected link (Translation-links mode), with
                  no model call.

Existing rows are all AI runs, so the column backfills to ``'ai'``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_fix_runs",
        sa.Column(
            "method",
            sa.String(length=12),
            nullable=False,
            server_default="ai",
        ),
    )


def downgrade() -> None:
    op.drop_column("link_fix_runs", "method")
