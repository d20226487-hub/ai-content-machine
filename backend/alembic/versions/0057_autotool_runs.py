"""autotool_runs + autotool_run_items — persisted Autotool send runs.

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-22

The Autotool "Send all" was synchronous (fire every per-domain-page POST inline,
show results, persist nothing, capped at 200 requests). This adds a run model so
a send becomes a background job with a progress page (like Bulk Runs): one
``autotool_run_items`` row per (domain, page), fired by a Celery worker that
bumps the run counters and finalises when sent+failed reaches total.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "autotool_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("table_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("target_url", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("site_column_id", sa.Integer(), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_autotool_runs_status", "autotool_runs", ["status"])

    op.create_table(
        "autotool_run_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("autotool_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site", sa.String(length=2048), nullable=False),
        sa.Column("start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_token", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("response_snippet", sa.Text(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_autotool_run_items_run_id", "autotool_run_items", ["run_id"])
    op.create_index(
        "ix_autotool_run_items_run_status", "autotool_run_items", ["run_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_autotool_run_items_run_status", table_name="autotool_run_items")
    op.drop_index("ix_autotool_run_items_run_id", table_name="autotool_run_items")
    op.drop_table("autotool_run_items")
    op.drop_index("ix_autotool_runs_status", table_name="autotool_runs")
    op.drop_table("autotool_runs")
