"""gdocs importer: store per-site structure + coverage count.

Revision ID: 0050
Revises: 0049
Create Date: 2026-06-04

Two additions for the Google-Docs importer:

* ``bulk_tables.gdocs_structure`` (JSONB, nullable) — the planned page list per
  site, kept so the table page can show a "Site structure" reference panel and
  the operator can supply it to AI. NULL for non-imported tables.
* ``gdocs_import_runs.total_structure_pages`` (int) — how many Structure entries
  the upload contained, so the run page can report coverage (rows built vs links
  vs planned pages) and warn when far fewer pages have a linked Doc than planned.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bulk_tables",
        sa.Column("gdocs_structure", JSONB, nullable=True),
    )
    op.add_column(
        "gdocs_import_runs",
        sa.Column(
            "total_structure_pages",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("gdocs_import_runs", "total_structure_pages")
    op.drop_column("bulk_tables", "gdocs_structure")
