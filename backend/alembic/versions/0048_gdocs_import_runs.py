"""gdocs_import_runs — Google-Docs → Custom-CMS import jobs.

Revision ID: 0048
Revises: 0047
Create Date: 2026-06-04

A background job that turns an uploaded Apps-Script JSON export (sheet rows +
each linked Google Doc as HTML) into a bulk-publish table in the Custom-CMS
layout. The run row carries the uploaded payload, live progress counters, the
resolved single/multi mode, aggregated warnings, and a SET-NULL link to the
bulk table it produced.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gdocs_import_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("table_name", sa.String(length=200), nullable=False),
        sa.Column("target_folder_id", sa.Integer, nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "result_table_id",
            sa.Integer,
            sa.ForeignKey("bulk_tables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("total_docs", sa.Integer, nullable=False, server_default="0"),
        sa.Column("docs_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("docs_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_pages", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_matched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pages_unmatched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_built", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_gdocs_import_runs_created",
        "gdocs_import_runs",
        [sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_gdocs_import_runs_created", table_name="gdocs_import_runs")
    op.drop_table("gdocs_import_runs")
