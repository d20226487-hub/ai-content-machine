"""Index usage_events for per-table cost aggregation.

Revision ID: 0065
Revises: 0064
Create Date: 2026-07-23

The table cost endpoint sums every ``source='bulk_cell'`` event for one
``source_ref->>'table_id'``, grouped by column. Migration 0063 added a partial
index keyed by (row_id, column_id) for the single-cell lookup, which can't
serve a table-wide scan — that query would fall back to a sequential scan over
``usage_events``, and that table grows by one row per LLM call forever.

This is the table-scoped counterpart: same partial predicate, keyed by
table_id then column_id so the GROUP BY is served directly.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_usage_events_bulk_table_cost
        ON usage_events (
            ((source_ref ->> 'table_id')),
            ((source_ref ->> 'column_id'))
        )
        WHERE source = 'bulk_cell'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_usage_events_bulk_table_cost")
