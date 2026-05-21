"""language_sync_runs + language_sync_results — persistent record of every
language-upsert batch we send to Custom CMS sites.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-21

Why these tables exist:
Each call to POST /publish/languages/sync used to just return the per-domain
results inline and disappear. Users asked for reporting — "which site got
which languages, when, and what was the outcome" — so the result of every
batch is now persisted.

Two-table split mirrors how publish_runs + publish_jobs work:
  * `language_sync_runs` — one row per batch: who triggered it, when,
    summary counts. Cheap to scan for the history listing page.
  * `language_sync_results` — one row per (run, domain) attempt: the
    languages we POSTed, the upstream HTTP status + body, ok/skip flags.
    Indexed by run_id so the detail page loads fast.

`created_by_id` is ON DELETE SET NULL so deleting a user doesn't cascade-
delete their sync history; `run_id` is ON DELETE CASCADE because a run's
results are meaningless without the parent.

`source` (on the run) is a short label for where the trigger came from
(`bulk_modal`, `standalone`, future entry points). Helps tell apart "a
publish-pre-flight" from "an ad-hoc fleet management" in the history list.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "language_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="bulk_modal"),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("ok_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("skip_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_language_sync_runs_created_at",
        "language_sync_runs",
        ["created_at"],
    )

    op.create_table(
        "language_sync_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=True),
        sa.Column("domain_name", sa.String(length=200), nullable=False),
        sa.Column(
            "languages",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["language_sync_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["domains.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_language_sync_results_run_id",
        "language_sync_results",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_language_sync_results_run_id", table_name="language_sync_results"
    )
    op.drop_table("language_sync_results")
    op.drop_index(
        "ix_language_sync_runs_created_at", table_name="language_sync_runs"
    )
    op.drop_table("language_sync_runs")
