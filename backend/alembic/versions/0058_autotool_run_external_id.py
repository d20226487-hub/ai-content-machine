"""autotool_runs.external_id — group all of a run's POSTs under one proxy id.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-23

The Autotool proxy returns an ``id`` from the FIRST request of a send; every
subsequent request must echo it in ``data.id`` so the proxy treats them as one
import job. We capture that id on the run after the first (leader) item and send
it with the rest. JSONB so the id round-trips with its exact JSON type (number
or string).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "autotool_runs",
        sa.Column("external_id", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("autotool_runs", "external_id")
