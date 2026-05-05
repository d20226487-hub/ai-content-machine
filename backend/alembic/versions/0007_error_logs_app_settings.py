"""error_logs + app_settings tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'null'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.execute(
        "INSERT INTO app_settings (key, value) VALUES "
        "('error_log_retention_days', '30'::jsonb)"
    )

    op.create_table(
        "error_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_error_logs_created_at_desc",
        "error_logs",
        [sa.text("created_at DESC")],
    )
    op.create_index("ix_error_logs_source", "error_logs", ["source"])
    op.create_index("ix_error_logs_category", "error_logs", ["category"])
    op.create_index("ix_error_logs_provider", "error_logs", ["provider"])
    op.create_index("ix_error_logs_user_id", "error_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_error_logs_user_id", table_name="error_logs")
    op.drop_index("ix_error_logs_provider", table_name="error_logs")
    op.drop_index("ix_error_logs_category", table_name="error_logs")
    op.drop_index("ix_error_logs_source", table_name="error_logs")
    op.drop_index("ix_error_logs_created_at_desc", table_name="error_logs")
    op.drop_table("error_logs")
    op.drop_table("app_settings")
