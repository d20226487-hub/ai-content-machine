"""Per-domain publish rate-limit overrides + global defaults in app_settings.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-03

Each column on `domains` is NULL by default — meaning "use the global default
from app_settings". The publish flow resolves: domain override → global default
→ hardcoded fallback.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULTS = [
    ("publish_default_requests_per_minute", "30"),
    ("publish_default_max_concurrency", "2"),
    ("publish_default_inter_request_delay_ms", "200"),
    ("publish_default_retry_max_attempts", "3"),
    ("publish_default_backoff_base_ms", "1000"),
    ("publish_default_backoff_jitter_ms", "250"),
    ("publish_default_respect_retry_after", "true"),
]


def upgrade() -> None:
    op.add_column(
        "domains",
        sa.Column("requests_per_minute", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("max_concurrency", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("inter_request_delay_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("retry_max_attempts", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("backoff_base_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("backoff_jitter_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "domains",
        sa.Column("respect_retry_after", sa.Boolean(), nullable=True),
    )

    for key, value in _DEFAULTS:
        op.execute(
            f"INSERT INTO app_settings (key, value) VALUES "
            f"('{key}', '{value}'::jsonb) ON CONFLICT (key) DO NOTHING"
        )


def downgrade() -> None:
    for key, _ in _DEFAULTS:
        op.execute(f"DELETE FROM app_settings WHERE key = '{key}'")
    op.drop_column("domains", "respect_retry_after")
    op.drop_column("domains", "backoff_jitter_ms")
    op.drop_column("domains", "backoff_base_ms")
    op.drop_column("domains", "retry_max_attempts")
    op.drop_column("domains", "inter_request_delay_ms")
    op.drop_column("domains", "max_concurrency")
    op.drop_column("domains", "requests_per_minute")
