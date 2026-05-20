"""publish_jobs.status_code — store the upstream HTTP status code.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-20

Before this migration, the exact upstream HTTP code was only retrievable
for FAILED rows (it got baked into the ``error`` text by the CMS clients
as ``f"HTTP {code}: ..."``). Successful rows lost the number entirely —
we only knew that ``200 <= code < 300`` because the success branch had
fired. That was the gap surfaced by a user asking "what status code did
the CRM return on job 323?" and getting back "some 2xx, I can't tell
which".

Nullable on purpose. Existing rows are backfilled to NULL — we have no
way to reconstruct the code retroactively, and the alternative (parsing
old ``error`` strings for "HTTP 422: ...") would be brittle and not
worth the migration cost. The UI treats NULL as "unknown" and falls
back to inferring 2xx for ``status='posted'`` or extracting from the
error text for ``status='failed'``.

SMALLINT is enough — HTTP status codes are 100–599. Two bytes vs four
for INTEGER, and SMALLINT communicates the domain constraint.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publish_jobs",
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publish_jobs", "status_code")
