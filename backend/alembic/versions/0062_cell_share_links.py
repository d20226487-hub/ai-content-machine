"""cell_share_links — public read-only share links for a single cell's preview.

Revision ID: 0062
Revises: 0061
Create Date: 2026-07-16

Lets a user hand someone WITHOUT an ACM account a link to one cell's rendered
content. The link is LIVE (it always renders the cell's current value), carries
an unguessable token, auto-expires (30 days by default) and can be revoked.

The row/column FKs cascade on delete, so removing the cell's row or column also
removes the link — a public URL can never outlive the thing it points at.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cell_share_links",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "table_id",
            sa.Integer(),
            sa.ForeignKey("bulk_tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Token lookup is the public hot path — unique doubles as its index.
    op.create_unique_constraint(
        "uq_cell_share_links_token", "cell_share_links", ["token"]
    )
    # "Is this cell already shared?" on the editor open.
    op.create_index(
        "ix_cell_share_links_cell",
        "cell_share_links",
        ["table_id", "row_id", "column_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cell_share_links_cell", table_name="cell_share_links")
    op.drop_constraint(
        "uq_cell_share_links_token", "cell_share_links", type_="unique"
    )
    op.drop_table("cell_share_links")
