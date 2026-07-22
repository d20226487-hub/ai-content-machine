"""Index usage_events for per-cell cost lookups.

Revision ID: 0063
Revises: 0062
Create Date: 2026-07-23

The cell editor asks "what did generating THIS cell cost?", which is the latest
``source='bulk_cell'`` event for one (row_id, column_id) out of ``source_ref``.
``source_ref`` is JSONB with no index, so that lookup is a sequential scan —
fine at a few dozen rows, but ``usage_events`` grows by one row per LLM call, so
in production it would degrade steadily.

A PARTIAL index (only 'bulk_cell' rows) keyed by the two extracted ids and
ordered by ``id DESC`` serves the "latest for this cell" query directly, and
stays small because it ignores every other usage source.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_usage_events_bulk_cell
        ON usage_events (
            ((source_ref ->> 'row_id')),
            ((source_ref ->> 'column_id')),
            id DESC
        )
        WHERE source = 'bulk_cell'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_usage_events_bulk_cell")
