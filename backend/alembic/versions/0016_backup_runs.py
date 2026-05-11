"""backup_runs table.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-07

History of every pg_dump invocation: when it ran, did it succeed, how large
was the dump, where did it land (local path, optional s3 key), what error
on failure. Surfaced in the admin Settings page.

Backup S3 config itself lives in `app_settings` under key `backup_config`,
so no schema change is needed for that.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        # 'running' | 'ok' | 'failed'
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("local_path", sa.String(500), nullable=True),
        sa.Column("s3_key", sa.String(500), nullable=True),
        # 'manual' | 'scheduled'
        sa.Column("trigger", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_backup_runs_started_at",
        "backup_runs",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backup_runs_started_at", table_name="backup_runs")
    op.drop_table("backup_runs")
