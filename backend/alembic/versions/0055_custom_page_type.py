"""custom_page_type — built-in Custom CMS page-type selector for bulk publish.

Revision ID: 0055
Revises: 0054
Create Date: 2026-06-19

A bulk-publish run against a Custom CMS domain can now target a built-in
"page type":

  * 'ordinary' (default) — keeps today's behavior; the run uses the domain's
    own endpoint_path + body_template.
  * 'match' — pins the hardcoded /add-sport-page endpoint + the sport field
    set (date / time / venue / group / odds_* …), overriding the domain config.

Stored on the run (so the worker knows which endpoint/template to use) and on
the mapping memo (so the modal pre-fills the last choice per table). Both
default to 'ordinary', so every pre-existing row keeps its current behavior.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_publish_runs",
        sa.Column(
            "custom_page_type",
            sa.String(length=20),
            nullable=False,
            server_default="ordinary",
        ),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column(
            "custom_page_type",
            sa.String(length=20),
            nullable=False,
            server_default="ordinary",
        ),
    )


def downgrade() -> None:
    op.drop_column("bulk_table_publish_mappings", "custom_page_type")
    op.drop_column("bulk_publish_runs", "custom_page_type")
