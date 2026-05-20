"""providers.extra_config_encrypted — Fernet-encrypted JSON for per-provider
structured creds (Vertex AI: service_account_json + project_id + location).

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-20

Vertex AI is the first provider that needs more than a single API key.
Two auth modes ship at once:

  * Service-account JSON (enterprise) — needs the SA JSON blob,
    project_id, and location. ACM mints a short-lived OAuth2 access token
    and POSTs against the regional aiplatform endpoint.
  * Vertex Express (API key) — uses the existing api_key_encrypted column
    against the global aiplatform endpoint. Nothing new needed.

The new column is a single Fernet-encrypted JSON blob so the schema stays
flat regardless of which (future) provider needs structured creds. Other
providers leave it NULL.

No data backfill — the existing 'vertex' seed row picks up NULL and the
admin fills it in via Settings.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("extra_config_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("providers", "extra_config_encrypted")
