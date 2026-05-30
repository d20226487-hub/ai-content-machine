"""bulk_table_cells.translations jsonb — on-demand translation memoization.

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-28

Why this exists:
The cell-editor modal has a Translate button that lets a colleague who
doesn't know the source language read the generated output in their own
language. Translations are view-only (do not overwrite the cell value)
but persist across reopens so we don't re-call the LLM each time.

Shape (jsonb, NULL when no translation has ever been requested):
    {
      "ru": {
        "text": "...",
        "provider_used": "openrouter",
        "model_used": "openai/gpt-4o-mini",
        "translated_at": "2026-05-28T14:32:00Z"
      },
      "pl": { ... }
    }

Keyed by lowercase BCP-47 language tag (or just "ru"/"en"/"pl"/...).
Multiple languages can coexist for a single cell — the picker in the
modal switches between cached panels and only triggers a fresh LLM
call when the requested language has no entry yet.

Server-side cache invalidation: when the underlying cell value changes
(manual edit or regenerate), the translations dict is cleared. That
logic lives in the upsert + bulk-generation worker paths, not here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_cells",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_cells", "translations")
