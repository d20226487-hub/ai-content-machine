"""link checker: multiple expected columns, include-OK toggle, detail codes.

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-30

Three evolutions to the link checker (still uncommitted feature, but it
already has real runs in dev, so this is a data-preserving forward
migration rather than a 0034 rewrite):

  * expected_column_id (single FK) → expected_column_ids (JSONB list) so a
    run can juxtapose against several expected-link columns (internal /
    external / product) unioned together.
  * include_ok — when crawling, also record healthy links as rows so the
    results table can show a full per-link status inventory.
  * link_check_violations.detail (English text) → detail_code (stable enum)
    so the frontend can localize the Detail column (RU/EN). status_code
    still carries the HTTP code.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- runs: expected_column_id -> expected_column_ids (list) ---
    op.add_column(
        "link_check_runs",
        sa.Column(
            "expected_column_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE link_check_runs
        SET expected_column_ids = CASE
            WHEN expected_column_id IS NULL THEN '[]'::jsonb
            ELSE jsonb_build_array(expected_column_id)
        END
        """
    )
    op.drop_column("link_check_runs", "expected_column_id")

    op.add_column(
        "link_check_runs",
        sa.Column(
            "include_ok", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )

    # --- violations: detail text -> detail_code enum ---
    op.add_column(
        "link_check_violations",
        sa.Column("detail_code", sa.String(length=24), nullable=True),
    )
    op.execute(
        """
        UPDATE link_check_violations SET detail_code = CASE
            WHEN problem = 'omitted'      THEN 'expected_missing'
            WHEN problem = 'hallucinated' THEN 'not_in_expected'
            WHEN problem = 'broken' AND status_code IS NOT NULL THEN 'http_error'
            WHEN problem = 'broken' AND detail ILIKE 'timeout%'     THEN 'timeout'
            WHEN problem = 'broken' AND detail ILIKE 'unreachable%' THEN 'unreachable'
            WHEN problem = 'broken' AND detail ILIKE 'blocked%'     THEN 'blocked'
            WHEN problem = 'ok'           THEN 'ok'
            ELSE 'unreachable'
        END
        """
    )
    op.drop_column("link_check_violations", "detail")


def downgrade() -> None:
    op.add_column(
        "link_check_violations",
        sa.Column("detail", sa.Text, nullable=True),
    )
    op.drop_column("link_check_violations", "detail_code")

    op.drop_column("link_check_runs", "include_ok")
    op.add_column(
        "link_check_runs",
        sa.Column("expected_column_id", sa.Integer, nullable=True),
    )
    op.execute(
        """
        UPDATE link_check_runs
        SET expected_column_id = (expected_column_ids->>0)::int
        WHERE jsonb_array_length(expected_column_ids) > 0
        """
    )
    op.create_foreign_key(
        "link_check_runs_expected_column_id_fkey",
        "link_check_runs",
        "bulk_table_columns",
        ["expected_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("link_check_runs", "expected_column_ids")
