"""Extend on-demand translation memoization to two more surfaces:
``generations.translations`` and ``prompt_versions.translations`` jsonb.

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-29

Why this exists:
The Translate button now lives in three places besides the bulk-table
cell editor: Single result (`/create`), prompt template detail
(`/prompts/[id]`), and the test-result inside `TestPromptModal`. For
the first two, the underlying entity has a stable id (Generation id,
PromptVersion id) so the translation can be memoized exactly the same
way bulk cells are — open the same saved generation tomorrow, see
yesterday's translation, no fresh LLM bill. The test modal stays
ephemeral by design; its translations go through `POST
/brain/translate-text` which doesn't persist.

Shape: same as bulk_table_cells.translations introduced in 0031 —

    {
      "ru": {
        "text": "...",
        "provider_used": "openrouter",
        "model_used": "openai/gpt-4o-mini",
        "translated_at": "2026-05-29T..."
      },
      "pl": { ... }
    }

Cache invalidation:
- Generations: the `output` text isn't updated after a saved-generation
  row is written, so there's no source-change path that needs to wipe
  the cache. The /generations PATCH endpoint only renames; if that ever
  changes (e.g. re-edit the output), clear `translations` there.
- PromptVersions: rows are IMMUTABLE by architecture (each save creates
  a new version, never mutates), so cache invalidation is structurally
  unnecessary. A new translate call against a different version_number
  is treated as a separate cell entirely.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generations",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "prompt_versions",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("prompt_versions", "translations")
    op.drop_column("generations", "translations")
