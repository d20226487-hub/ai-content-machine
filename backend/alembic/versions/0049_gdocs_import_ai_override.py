"""gdocs_import_runs — per-import AI provider/model override.

Revision ID: 0049
Revises: 0048
Create Date: 2026-06-04

The Google-Docs importer cleans meta + pairs Structure pages to Docs with an
LLM. Until now it silently used the first-enabled provider and that provider's
default model. These two nullable columns let a single import pin its own
provider/model from a picker on the upload modal. NULL = keep the prior
behavior (first-enabled provider + its default model), so existing runs and
"leave it on default" uploads are unaffected.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gdocs_import_runs",
        sa.Column("provider_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "gdocs_import_runs",
        sa.Column("model", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gdocs_import_runs", "model")
    op.drop_column("gdocs_import_runs", "provider_code")
