"""link checker: distributed crawl — work-unit table + progress stamp.

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-30

The crawl was a single Celery task (one worker, 10 in-flight, 2000-link
cap). This scales it out and makes it crash-resumable:

  * ``link_check_crawl_targets`` — one row per UNIQUE crawlable URL in a run,
    carrying the occurrences it appears in, a ``chunk_index`` (which child
    task owns it), and its crawl result. ``state`` flips pending→done; a
    redelivered/resumed chunk re-queries only ``pending`` rows, so it's
    idempotent (no double-counting, no duplicate violations).
  * ``link_check_runs.last_progress_at`` — bumped on every counter update so
    a watchdog can spot a stalled run and re-enqueue its pending chunks.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "link_check_runs",
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "link_check_crawl_targets",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("link_check_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        # 'pending' | 'done'
        sa.Column(
            "state", sa.String(length=12), nullable=False, server_default="pending"
        ),
        sa.Column("ok", sa.Boolean, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("detail_code", sa.String(length=24), nullable=True),
        # [{row_id, row_position, column_id, column_name}, …] — the cells this
        # URL appears in, so a child can write occurrence violations directly.
        sa.Column(
            "occurrences",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("run_id", "url", name="uq_lc_targets_run_url"),
    )
    # Child query: pending targets for (run, chunk). Also serves the
    # distinct-pending-chunks lookup the watchdog/resume use.
    op.create_index(
        "ix_lc_targets_run_chunk_state",
        "link_check_crawl_targets",
        ["run_id", "chunk_index", "state"],
    )
    # Finalizer's "any pending left?" count.
    op.create_index(
        "ix_lc_targets_run_state",
        "link_check_crawl_targets",
        ["run_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_lc_targets_run_state", table_name="link_check_crawl_targets")
    op.drop_index(
        "ix_lc_targets_run_chunk_state", table_name="link_check_crawl_targets"
    )
    op.drop_table("link_check_crawl_targets")
    op.drop_column("link_check_runs", "last_progress_at")
