"""Store per-cell applied_ops on structure_format_cells (filterable).

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-01

The run page can filter the result table by which mini-tool was applied to a
row. ``applied_ops`` was computed at read time, which can't be filtered in SQL
across pages — so we persist it per cell (the subset of the run's transforms
that actually changed THAT cell). Existing 'done' rows are backfilled by
re-tracing their ``old_value`` through the run's operations.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "structure_format_cells",
        sa.Column(
            "applied_ops",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Backfill existing changed cells (no-op on a fresh DB). Re-trace each
    # cell's old_value through its run's operations to recover which ones
    # actually changed it.
    from app.services.structure_format import apply_operations_traced

    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT c.id, c.old_value, r.operations
            FROM structure_format_cells c
            JOIN structure_format_runs r ON r.id = c.run_id
            WHERE c.state = 'done'
            """
        )
    ).fetchall()
    for cid, old_value, operations in rows:
        ops = [str(o) for o in (operations or [])]
        _, applied = apply_operations_traced(old_value or "", ops)
        conn.execute(
            text(
                "UPDATE structure_format_cells SET applied_ops = :ops "
                "WHERE id = :id"
            ),
            {"ops": json.dumps(applied), "id": cid},
        )


def downgrade() -> None:
    op.drop_column("structure_format_cells", "applied_ops")
