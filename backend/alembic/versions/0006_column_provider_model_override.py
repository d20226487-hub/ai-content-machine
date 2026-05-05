"""Per-column provider_code + model override on bulk_table_columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_table_columns",
        sa.Column("provider_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "bulk_table_columns",
        sa.Column("model", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_columns", "model")
    op.drop_column("bulk_table_columns", "provider_code")
