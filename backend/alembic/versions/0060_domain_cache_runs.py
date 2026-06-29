"""domain_cache_runs + domain_cache_run_items — bulk Custom-CMS cache clear/warm.

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-27

Backs a background job that bulk-hits the Custom CMS cache endpoints
(/index.php?_clear_cache and ?__warm_cache) across selected domains, with a
progress page like Bulk Runs / Autotool Runs. One ``domain_cache_run_items`` row
per selected Custom-CMS domain; a Celery worker fires the chosen endpoint(s)
reusing the domain's stored credentials and bumps the run counters.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_cache_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "skipped_unsupported", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_domain_cache_runs_status", "domain_cache_runs", ["status"]
    )

    op.create_table(
        "domain_cache_run_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("domain_cache_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("domain_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("base_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("clear_status_code", sa.Integer(), nullable=True),
        sa.Column("warm_status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_domain_cache_run_items_run_id", "domain_cache_run_items", ["run_id"]
    )
    op.create_index(
        "ix_domain_cache_run_items_run_status",
        "domain_cache_run_items",
        ["run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_domain_cache_run_items_run_status", table_name="domain_cache_run_items"
    )
    op.drop_index(
        "ix_domain_cache_run_items_run_id", table_name="domain_cache_run_items"
    )
    op.drop_table("domain_cache_run_items")
    op.drop_index("ix_domain_cache_runs_status", table_name="domain_cache_runs")
    op.drop_table("domain_cache_runs")
