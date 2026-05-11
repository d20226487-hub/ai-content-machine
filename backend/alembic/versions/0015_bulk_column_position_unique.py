"""Unique (table_id, position) on bulk_table_columns.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-07

Closes a long-standing race: two concurrent "add column" requests both read
`SELECT max(position)+1` and INSERT the same value, ending with two columns
sharing a position. The UI then renders them in a non-deterministic order.

Constraints can't be added blindly on prod — there may already be duplicates
from past races. The migration first re-numbers positions deterministically
within each table so they become 0..N-1 with ties broken by id, then adds
the unique constraint. Re-numbering preserves user-visible order: rows are
ordered by (position, id), which is the same order the UI rendered before.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Renumber positions per table to 0..N-1, ordered by current position
    # then id. ROW_NUMBER() is Postgres-only; we rely on Postgres elsewhere
    # in this codebase (jsonb, advisory locks) so this is fine.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY table_id
                    ORDER BY position, id
                ) - 1 AS new_position
            FROM bulk_table_columns
        )
        UPDATE bulk_table_columns AS c
        SET position = ranked.new_position
        FROM ranked
        WHERE c.id = ranked.id
          AND c.position IS DISTINCT FROM ranked.new_position;
        """
    )

    op.create_unique_constraint(
        "uq_bulk_columns_table_position",
        "bulk_table_columns",
        ["table_id", "position"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_bulk_columns_table_position",
        "bulk_table_columns",
        type_="unique",
    )
    # Renumbering is not reversible; leave the renumbered values in place.
