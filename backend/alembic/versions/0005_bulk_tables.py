"""bulk_tables, bulk_table_columns, bulk_table_rows, bulk_table_cells

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bulk_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_bulk_tables_created_by_id", "bulk_tables", ["created_by_id"])

    op.create_table(
        "bulk_table_columns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="input"),
        sa.Column(
            "prompt_id",
            sa.Integer(),
            sa.ForeignKey("prompts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_version_number", sa.Integer(), nullable=True),
        sa.Column(
            "variable_map",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_bulk_table_columns_table_id", "bulk_table_columns", ["table_id"])

    op.create_table(
        "bulk_table_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_bulk_table_rows_table_id", "bulk_table_rows", ["table_id"])

    op.create_table(
        "bulk_table_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "row_id",
            sa.Integer(),
            sa.ForeignKey("bulk_table_rows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "column_id",
            sa.Integer(),
            sa.ForeignKey("bulk_table_columns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="empty"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(length=120), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("row_id", "column_id", name="uq_bulk_cells_row_column"),
    )
    op.create_index("ix_bulk_table_cells_row_id", "bulk_table_cells", ["row_id"])
    op.create_index("ix_bulk_table_cells_column_id", "bulk_table_cells", ["column_id"])


def downgrade() -> None:
    op.drop_index("ix_bulk_table_cells_column_id", table_name="bulk_table_cells")
    op.drop_index("ix_bulk_table_cells_row_id", table_name="bulk_table_cells")
    op.drop_table("bulk_table_cells")
    op.drop_index("ix_bulk_table_rows_table_id", table_name="bulk_table_rows")
    op.drop_table("bulk_table_rows")
    op.drop_index("ix_bulk_table_columns_table_id", table_name="bulk_table_columns")
    op.drop_table("bulk_table_columns")
    op.drop_index("ix_bulk_tables_created_by_id", table_name="bulk_tables")
    op.drop_table("bulk_tables")
