"""generations table for saved Single-mode outputs

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "prompt_id",
            sa.Integer(),
            sa.ForeignKey("prompts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_version_number", sa.Integer(), nullable=True),
        sa.Column("prompt_name_snapshot", sa.String(length=200), nullable=False),
        sa.Column("rendered_prompt", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("model_used", sa.String(length=120), nullable=False),
        sa.Column("finish_reason", sa.String(length=50), nullable=True),
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
    op.create_index("ix_generations_prompt_id", "generations", ["prompt_id"])
    op.create_index("ix_generations_created_by_id", "generations", ["created_by_id"])


def downgrade() -> None:
    op.drop_index("ix_generations_created_by_id", table_name="generations")
    op.drop_index("ix_generations_prompt_id", table_name="generations")
    op.drop_table("generations")
