"""language-sync: background-job columns (status + progress + per-result state).

Revision ID: 0054
Revises: 0053
Create Date: 2026-06-11

Why this exists:
The multi-domain language sync used to run fully synchronously — one POST
fanned out to every target site and blocked until all of them answered. For
an 80-site batch that's a long request with no progress feedback and no way
to re-attempt just the sites that failed.

This migration turns a run into a pollable background job (same shape as the
Structure & Formatting / Link-Checker runs):

  language_sync_runs
    + status            'queued' | 'running' | 'done'
    + started_at        when the worker picked it up
    + finished_at       when it reached a terminal state
    + last_progress_at  bumped each batch (lets a future watchdog spot stalls)

  language_sync_results
    + state             'pending' (not yet attempted) | 'done' (attempted)

Existing historical runs were synchronous and already complete, so both new
status/state columns default to 'done' — every pre-existing row reads back as
a finished run with finished results. Forward-only, data-preserving.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "language_sync_runs",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="done",
        ),
    )
    op.add_column(
        "language_sync_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "language_sync_runs",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "language_sync_runs",
        sa.Column(
            "last_progress_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "language_sync_results",
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="done",
        ),
    )
    # The worker repeatedly claims "the next pending results for this run";
    # this partial-ish index serves that scan without walking finished rows.
    op.create_index(
        "ix_language_sync_results_run_state",
        "language_sync_results",
        ["run_id", "state"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_language_sync_results_run_state",
        table_name="language_sync_results",
    )
    op.drop_column("language_sync_results", "state")
    op.drop_column("language_sync_runs", "last_progress_at")
    op.drop_column("language_sync_runs", "finished_at")
    op.drop_column("language_sync_runs", "started_at")
    op.drop_column("language_sync_runs", "status")
