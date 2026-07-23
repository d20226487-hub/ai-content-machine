"""Grounding result cache.

Revision ID: 0068
Revises: 0067
Create Date: 2026-07-23

``grounding_cache`` — memoized grounded generations. A grounded provider call is
billable (the Google Search tool carries a per-request surcharge), so its result
(value + cited sources) is cached keyed by a SHA-256 of the rendered prompt +
model + grounding source. An identical re-run or a duplicate-input row reuses it
and pays nothing. Entries past the service TTL are ignored and swept by a beat
task, so the table can be dropped/rebuilt freely.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0068"
down_revision: Union[str, None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grounding_cache",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("finish_reason", sa.String(length=40), nullable=True),
        sa.Column("sources", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_grounding_cache_cache_key", "grounding_cache", ["cache_key"], unique=True
    )
    op.create_index(
        "ix_grounding_cache_created_at", "grounding_cache", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_grounding_cache_created_at", table_name="grounding_cache")
    op.drop_index("ix_grounding_cache_cache_key", table_name="grounding_cache")
    op.drop_table("grounding_cache")
