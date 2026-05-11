"""usage_events: per-call LLM spend log.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-10

One row per successful LLM call from any of three sources:
  * 'single'    - single-mode /generate/single
  * 'bulk_cell' - bulk-table cell generation worker
  * 'ai_assist' - prompt-creation AI assist

`cost_usd` is computed at write time from app_settings.pricing (per
provider:model rate). When pricing is missing for a model, cost_usd is
NULL — the event is still recorded (token counts preserved) and the
admin sees "(no pricing)" in the spend view until they fill in the rate.

Aggregation queries use indexes on (user_id, created_at) to keep the
daily/weekly/monthly window views fast.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # SET NULL so deleting a user keeps their historical spend recorded
        # (anonymised via NULL user_id) instead of cascade-deleting the log.
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider_code", sa.String(50), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        # Token counts. None when the provider didn't return them.
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        # USD with 6 decimal places — covers per-token billing for cheap
        # models without rounding to zero. NULL means "we have no rate
        # configured for this provider:model pair right now".
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        # 'single' | 'bulk_cell' | 'ai_assist'
        sa.Column("source", sa.String(20), nullable=False),
        # Free-form: {prompt_id, version_number, table_id, row_id, column_id, ...}
        sa.Column(
            "source_ref",
            sa.dialects.postgresql.JSONB,
            nullable=True,
        ),
    )
    # Per-user time-window aggregations are the hot read path — index for it.
    op.create_index(
        "ix_usage_events_user_created",
        "usage_events",
        ["user_id", "created_at"],
    )
    # Useful for admin "all users this month" queries that ignore user.
    op.create_index(
        "ix_usage_events_created_at",
        "usage_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_user_created", table_name="usage_events")
    op.drop_table("usage_events")
