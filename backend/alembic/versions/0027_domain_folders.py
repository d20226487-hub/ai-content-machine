"""domain_folders + domains.folder_id — Drive-style tree for /publish/domains.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-20

Mirrors the Prompts categories tree (categories.parent_id self-FK,
no separate root row — null parent_id = top-level). Library uses a
flat folder model; we deliberately pick the tree shape here so a
"Project" can be a top-level folder with optional sub-folders inside
(matching how the user described their fleet — a domain per
sub-property, grouped by client, grouped by region).

Two FK choices worth pinning:
  - domain_folders.parent_id ON DELETE RESTRICT
    The folder-CRUD endpoint already refuses to delete a non-empty
    folder (matches Prompts categories). RESTRICT at the DB level
    is belt-and-braces against a direct SQL delete bypassing that
    check.
  - domains.folder_id ON DELETE SET NULL
    A different policy on purpose: if a folder somehow got force-
    deleted (e.g. via an admin DBA action) the domains inside it
    should fall back to "no folder" rather than being deleted
    themselves. Domains are precious data; folders are organization.

The new domains.folder_id column is nullable + has no default —
all existing domains land in the implicit root (NULL) folder, and
the user moves them into folders by hand. No backfill needed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("domain_folders.id", ondelete="RESTRICT"),
            nullable=True,
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
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_domain_folders_parent_id", "domain_folders", ["parent_id"]
    )

    op.add_column(
        "domains",
        sa.Column(
            "folder_id",
            sa.Integer(),
            sa.ForeignKey("domain_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Index so the list endpoint's `?folder_id=N` filter (and the
    # `?folder_id is null` "root" case) doesn't seq-scan the table once
    # the user has thousands of domains.
    op.create_index("ix_domains_folder_id", "domains", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_domains_folder_id", table_name="domains")
    op.drop_column("domains", "folder_id")
    op.drop_index("ix_domain_folders_parent_id", table_name="domain_folders")
    op.drop_table("domain_folders")
