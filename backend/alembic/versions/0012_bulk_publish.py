"""bulk_publish_runs + bulk_table_publish_mappings.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-03

A run is the parent record for a single "publish this table to that domain"
operation. Child publish_jobs link back via source_ref->>'run_id'.

The mapping table is a per-(table, domain, profile) memo so the BulkPublishModal
can auto-prefill column→field maps the next time the user publishes the same
table to the same destination. profile_name uses '' for Custom CMS (no profile
concept) so the composite primary key stays clean.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulk_publish_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # '' for Custom CMS (no profile concept). Real profile name for WP.
        sa.Column(
            "profile_name",
            sa.String(length=200),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("language", sa.String(length=20), nullable=True),
        # 'all' | 'selected' | 'range'
        sa.Column("row_filter", sa.String(length=20), nullable=False),
        # When row_filter='selected' → {"row_ids": [..]}; when 'range' → {"start": N, "end": M}.
        sa.Column(
            "selection",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # 'all' | 'unpublished' | 'failed'
        sa.Column(
            "cell_filter",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'all'"),
        ),
        # {fieldKey: column_id}
        sa.Column(
            "field_to_column",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # {"post_id_target": column_id, "post_url_target": column_id}
        sa.Column(
            "back_fill",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # 'queued'|'running'|'paused'|'cancelled'|'done'|'failed'
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("done", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bulk_publish_runs_created_at_desc",
        "bulk_publish_runs",
        [sa.text("created_at DESC")],
    )
    op.create_index("ix_bulk_publish_runs_table_id", "bulk_publish_runs", ["table_id"])
    op.create_index("ix_bulk_publish_runs_status", "bulk_publish_runs", ["status"])
    op.create_index(
        "ix_bulk_publish_runs_created_by_id", "bulk_publish_runs", ["created_by_id"]
    )

    op.create_table(
        "bulk_table_publish_mappings",
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "domain_id",
            sa.Integer(),
            sa.ForeignKey("domains.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "profile_name",
            sa.String(length=200),
            primary_key=True,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "field_to_column",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "back_fill",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("language", sa.String(length=20), nullable=True),
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


def downgrade() -> None:
    op.drop_table("bulk_table_publish_mappings")
    op.drop_index("ix_bulk_publish_runs_created_by_id", table_name="bulk_publish_runs")
    op.drop_index("ix_bulk_publish_runs_status", table_name="bulk_publish_runs")
    op.drop_index("ix_bulk_publish_runs_table_id", table_name="bulk_publish_runs")
    op.drop_index(
        "ix_bulk_publish_runs_created_at_desc", table_name="bulk_publish_runs"
    )
    op.drop_table("bulk_publish_runs")
