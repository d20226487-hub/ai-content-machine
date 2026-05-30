"""link_check_runs + link_check_violations — bulk link checker content tool.

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-30

Why this exists:
Generated content frequently mishandles links — omits ones that should be
inserted, invents (hallucinates) URLs, or typos a real link into a 404.
The Link Checker (content tool #2) scans selected column(s) and flags rows
with violations via two mechanisms:
  * juxtapose — compare links extracted from the output column(s) against a
    per-row "expected links" column (catches omitted + hallucinated)
  * crawl — fetch each link and check the HTTP status (catches typos / dead
    links)

Crawling hits the network per link, so a check runs as a background Celery
job with live progress — mirroring bulk_generation_runs (status + counters
+ cancel). ``link_check_runs`` holds the config + progress + summary
counters; ``link_check_violations`` holds one row per flagged link. History
is persistent (CASCADE-deleted with the table), like find_replace_runs.

Violations snapshot ``row_position`` + ``column_name`` so the results table
renders without extra joins and survives later renames/reorders.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "link_check_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # queued → running → (cancelled | done | failed)
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="queued"
        ),
        sa.Column(
            "column_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "expected_column_id",
            sa.Integer,
            sa.ForeignKey("bulk_table_columns.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "check_juxtapose",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "check_crawl", sa.Boolean, nullable=False, server_default=sa.false()
        ),
        sa.Column("total_links", sa.Integer, nullable=False, server_default="0"),
        sa.Column("crawled", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("broken_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("omitted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "hallucinated_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_link_check_runs_table_created",
        "link_check_runs",
        ["table_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "link_check_violations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("link_check_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Plain ints (no FK): the row/column may be deleted later; the
        # snapshot fields still render and click-to-edit just no-ops then.
        sa.Column("row_id", sa.Integer, nullable=False),
        sa.Column("row_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("column_id", sa.Integer, nullable=False),
        sa.Column("column_name", sa.String(length=120), nullable=False),
        # 'omitted' | 'hallucinated' | 'broken'
        sa.Column("problem", sa.String(length=16), nullable=False),
        sa.Column("link", sa.Text, nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_link_check_violations_run", "link_check_violations", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_link_check_violations_run", table_name="link_check_violations"
    )
    op.drop_table("link_check_violations")
    op.drop_index("ix_link_check_runs_table_created", table_name="link_check_runs")
    op.drop_table("link_check_runs")
