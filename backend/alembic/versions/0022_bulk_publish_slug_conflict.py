"""Bulk publish — duplicate-slug handling on Create.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-12

Adds ``on_slug_conflict`` to ``bulk_publish_runs`` and
``bulk_table_publish_mappings``:

  'create'  Always POST a new post. WP auto-suffixes colliding slugs
            (``canada`` → ``canada-2``). Backward-compatible default.
  'skip'    Pre-check the slug via /wp/v2/{type}?slug=…&lang=…. If a
            post exists, record the row as ``skipped`` (run counter
            bumps, no PublishJob 'posting'). Use when you want to
            re-run a generation step without re-publishing what's
            already there.
  'update'  Pre-check the slug. If a post exists, PATCH it (same
            semantics as Update mode — empty cells left unchanged).
            If not, POST a new one. True upsert.

Only valid when operation='create' (Update mode by definition already
resolves an existing post; combining would conflict). Requires that
the run's field_to_column map includes 'slug' — without a slug there's
nothing to pre-check.

The duplicate check reuses ``WordPressClient.find_post`` with
``effective_language``, so on Polylang/WPML domains the lookup is
correctly scoped to the row's target language: an EN ``canada`` post
does NOT trigger a duplicate for a new RU ``canada`` post.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_publish_runs",
        sa.Column(
            "on_slug_conflict",
            sa.String(16),
            nullable=False,
            server_default="create",
        ),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column(
            "on_slug_conflict",
            sa.String(16),
            nullable=False,
            server_default="create",
        ),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_publish_mappings", "on_slug_conflict")
    op.drop_column("bulk_publish_runs", "on_slug_conflict")
