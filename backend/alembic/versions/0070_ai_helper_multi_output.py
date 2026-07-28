"""AI Helper v1.1: multi-column output + two engines.

Revision ID: 0070
Revises: 0069
Create Date: 2026-07-24

v1 (0069) wrote a single target column per run. v1.1 lets one run write/edit
MULTIPLE columns, mixing modes, via two engines chosen per run:

  * ``engine`` — 'structured' (one AI call/row returning a JSON object whose
    keys route to the output columns) or 'per_output' (one focused AI call per
    output column).
  * ``outputs`` — the list of output columns, each ``{column_id, mode
    ('write'|'edit'), key, prompt}``. ``key`` is the JSON key for the structured
    engine; ``prompt`` is the per-output prompt for the per_output engine.

v1's ``target_column_id`` / ``mode`` columns are kept: legacy runs (outputs=[])
are read as a synthesized one-entry outputs list, so old runs and their revert
snapshots keep working. Cells are already keyed ``(run_id, row_id, column_id)``,
so seeding one ``AiHelperCell`` per (row, output column) gives per-column revert
for free. Existing rows default to ``engine='per_output'`` — a one-output run on
that engine reproduces v1 behaviour exactly.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0070"
down_revision: Union[str, None] = "0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_helper_runs",
        # 'structured' (1 call/row → JSON) | 'per_output' (1 call per output).
        sa.Column(
            "engine",
            sa.String(length=16),
            nullable=False,
            server_default="per_output",
        ),
    )
    op.add_column(
        "ai_helper_runs",
        # [{column_id, mode('write'|'edit'), key, prompt}]. Empty for legacy
        # runs (read via the target_column_id/mode fallback).
        sa.Column(
            "outputs",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_helper_runs", "outputs")
    op.drop_column("ai_helper_runs", "engine")
