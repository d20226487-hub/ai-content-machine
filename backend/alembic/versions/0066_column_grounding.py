"""Per-column grounding + per-cell grounding sources.

Revision ID: 0066
Revises: 0065
Create Date: 2026-07-23

Adds the first slice of "grounded research" (Stage 1):

  * ``bulk_table_columns.grounding`` — per-column override, sitting beside the
    existing ``provider_code`` / ``model`` / ``max_output_tokens`` overrides.
    NULL = off. The only value wired today is ``'google_search'`` (Gemini on
    Vertex uses Google Search as a tool); the column is a plain String so
    later sources (``'vertex_ai_search'``) need no migration.
  * ``bulk_table_cells.grounding_sources`` — JSONB holding what a grounded
    generation cited: ``{"queries": [...], "sources": [{"uri","title"}, ...],
    "retrieved_at": "<ISO>"}``. NULL when the cell was never grounded. Cleared
    on the next write of ``value`` (same lifecycle as ``translations``). The
    source URIs are Vertex redirect links that expire (~30 days), so this is a
    record of provenance, not a durable citation store.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_columns",
        sa.Column("grounding", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "bulk_table_cells",
        sa.Column("grounding_sources", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_cells", "grounding_sources")
    op.drop_column("bulk_table_columns", "grounding")
