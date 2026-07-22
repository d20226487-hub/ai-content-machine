"""Configurable output-token cap for bulk generation.

Revision ID: 0064
Revises: 0063
Create Date: 2026-07-23

Bulk cell generation hardcoded ``max_output_tokens=2048`` for every call,
which caps a generated article at roughly 5.7k characters of HTML and silently
truncates anything longer. Worse, on models that bill reasoning against the
same budget (Gemini 2.5, Claude Sonnet 5) the *visible* ceiling is 2048 minus
however much the model thought that run — so the same prompt truncates at a
different length on every row.

This adds:
  * ``bulk_table_columns.max_output_tokens`` — per-column override, mirroring
    the existing per-column ``provider_code`` / ``model`` overrides. NULL means
    "fall back to the global default".
  * ``generation_default_max_output_tokens`` — the global default, seeded to
    8192 (4x the old hardcoded value).
  * ``generation_thinking_budget`` — reasoning-token allowance. Seeded to NULL
    (send nothing, use the model's default) so upgrading cannot change
    behaviour on a model whose thinking API differs from Gemini 2.5's.
  * ``bulk_table_cells.finish_reason`` — why the model stopped. Every provider
    already returns this ("MAX_TOKENS" / "length" / "max_tokens" for a cut-off)
    and it was being discarded, which is why hitting the ceiling looked
    identical to finishing normally. Stored raw rather than as a boolean so the
    non-truncation reasons (SAFETY, RECITATION, …) are diagnosable too.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0064"
down_revision: Union[str, None] = "0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_columns",
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bulk_table_cells",
        sa.Column("finish_reason", sa.String(length=40), nullable=True),
    )
    op.execute(
        "INSERT INTO app_settings (key, value) VALUES "
        "('generation_default_max_output_tokens', '8192'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "INSERT INTO app_settings (key, value) VALUES "
        "('generation_thinking_budget', 'null'::jsonb) "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM app_settings WHERE key IN "
        "('generation_default_max_output_tokens', 'generation_thinking_budget')"
    )
    op.drop_column("bulk_table_cells", "finish_reason")
    op.drop_column("bulk_table_columns", "max_output_tokens")
