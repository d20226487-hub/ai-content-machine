"""csv_export_jobs + csv_export_blobs — background CSV export.

Revision ID: 0061
Revises: 0060
Create Date: 2026-06-27

Decouples the table-page CSV export from a single long HTTP download (which trips
the front proxy/CDN response timeout on large tables): a Celery worker builds the
CSV, gzips it, and stores the bytes here; the browser downloads the pre-built
blob in a fast separate request. Blob lives in its own table so status polling
stays light.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "csv_export_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("table_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_csv_export_jobs_status", "csv_export_jobs", ["status"])
    op.create_index(
        "ix_csv_export_jobs_created_by", "csv_export_jobs", ["created_by_id"]
    )
    op.create_index("ix_csv_export_jobs_table", "csv_export_jobs", ["table_id"])

    op.create_table(
        "csv_export_blobs",
        sa.Column(
            "job_id",
            sa.BigInteger(),
            sa.ForeignKey("csv_export_jobs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content_gzip", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("csv_export_blobs")
    op.drop_index("ix_csv_export_jobs_table", table_name="csv_export_jobs")
    op.drop_index("ix_csv_export_jobs_created_by", table_name="csv_export_jobs")
    op.drop_index("ix_csv_export_jobs_status", table_name="csv_export_jobs")
    op.drop_table("csv_export_jobs")
