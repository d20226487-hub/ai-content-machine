"""Multi-site bulk publish: domain.name uniqueness + per-row resolution.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-07

Three things in one migration:

1. ``domains.name`` UNIQUE.
   Multi-mode bulk publish resolves each row to a domain by name. If two
   domains share a name, lookup is ambiguous. We dedupe existing rows by
   appending " (N)" to all but the lowest-id holder of each name, then add
   the constraint. The renames are deterministic and survive a re-run.

2. ``bulk_publish_runs`` gains ``mode`` plus two FK columns
   (``domain_column_id``, ``profile_column_id``) pointing at the bulk-table
   column whose cell value provides domain/profile per-row in multi mode.
   ``domain_id`` becomes nullable since multi-mode runs have no fixed domain.

3. ``bulk_table_publish_mappings`` gains a ``mode`` column plus
   ``domain_column_id`` / ``profile_column_id``. The old composite primary
   key (table_id, domain_id, profile_name) doesn't fit the multi shape, so
   we replace it with a synthetic ``id`` PK and use partial unique indexes:
   one for single mode keyed on the old triple, one for multi mode keyed
   on (table_id) alone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Dedupe domains.name then add the unique constraint.
    #    For each duplicate name, keep the lowest id as-is and rename the rest
    #    to "<name> (2)", "<name> (3)", … using a stable ROW_NUMBER ordering.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, name,
                   ROW_NUMBER() OVER (PARTITION BY name ORDER BY id) AS rn
            FROM domains
        )
        UPDATE domains AS d
        SET name = ranked.name || ' (' || ranked.rn || ')'
        FROM ranked
        WHERE d.id = ranked.id AND ranked.rn > 1;
        """
    )
    op.create_unique_constraint("uq_domains_name", "domains", ["name"])

    # 2) bulk_publish_runs new columns + relax NOT NULL on domain_id.
    op.add_column(
        "bulk_publish_runs",
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            server_default="single",
        ),
    )
    op.add_column(
        "bulk_publish_runs",
        sa.Column("domain_column_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bulk_publish_runs",
        sa.Column("profile_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_bulk_publish_runs_domain_column_id",
        "bulk_publish_runs",
        "bulk_table_columns",
        ["domain_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_bulk_publish_runs_profile_column_id",
        "bulk_publish_runs",
        "bulk_table_columns",
        ["profile_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # domain_id was already nullable in the model (`Mapped[int | None]`) but
    # the SQL column may be NOT NULL on older deployments. Make it
    # explicitly nullable; no-op if it already is.
    op.alter_column(
        "bulk_publish_runs",
        "domain_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # 3) bulk_table_publish_mappings restructure.
    #    Drop the old composite PK, add a synthetic id PK, mode + per-row
    #    columns, then replace the uniqueness with partial indexes.
    op.execute(
        "ALTER TABLE bulk_table_publish_mappings "
        "DROP CONSTRAINT bulk_table_publish_mappings_pkey"
    )
    # Sequence MUST exist before the column that defaults to nextval(...).
    op.execute("CREATE SEQUENCE IF NOT EXISTS bulk_table_publish_mappings_id_seq")
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column(
            "id",
            sa.BigInteger(),
            nullable=False,
            autoincrement=True,
            server_default=sa.text(
                "nextval('bulk_table_publish_mappings_id_seq'::regclass)"
            ),
        ),
    )
    # Attach the sequence to the column so DROP TABLE drops it too.
    op.execute(
        "ALTER SEQUENCE bulk_table_publish_mappings_id_seq "
        "OWNED BY bulk_table_publish_mappings.id"
    )
    op.create_primary_key(
        "bulk_table_publish_mappings_pkey", "bulk_table_publish_mappings", ["id"]
    )

    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            server_default="single",
        ),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column("domain_column_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "bulk_table_publish_mappings",
        sa.Column("profile_column_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_btpm_domain_column_id",
        "bulk_table_publish_mappings",
        "bulk_table_columns",
        ["domain_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_btpm_profile_column_id",
        "bulk_table_publish_mappings",
        "bulk_table_columns",
        ["profile_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Old domain_id / profile_name remain — used by single mode only.
    op.alter_column(
        "bulk_table_publish_mappings",
        "domain_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "bulk_table_publish_mappings",
        "profile_name",
        existing_type=sa.String(200),
        nullable=True,
    )

    # Partial unique indexes — one shape per mode.
    op.execute(
        "CREATE UNIQUE INDEX uq_btpm_single ON bulk_table_publish_mappings "
        "(table_id, domain_id, profile_name) WHERE mode = 'single'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_btpm_multi ON bulk_table_publish_mappings "
        "(table_id) WHERE mode = 'multi'"
    )


def downgrade() -> None:
    # 3) Reverse mappings restructure.
    op.execute("DROP INDEX IF EXISTS uq_btpm_multi")
    op.execute("DROP INDEX IF EXISTS uq_btpm_single")
    op.drop_constraint(
        "fk_btpm_profile_column_id",
        "bulk_table_publish_mappings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_btpm_domain_column_id",
        "bulk_table_publish_mappings",
        type_="foreignkey",
    )
    op.drop_column("bulk_table_publish_mappings", "profile_column_id")
    op.drop_column("bulk_table_publish_mappings", "domain_column_id")
    op.drop_column("bulk_table_publish_mappings", "mode")
    # Restore old composite PK. Rows where domain_id IS NULL or profile_name
    # IS NULL must be dropped first to satisfy NOT NULL.
    op.execute(
        "DELETE FROM bulk_table_publish_mappings "
        "WHERE domain_id IS NULL OR profile_name IS NULL"
    )
    op.alter_column(
        "bulk_table_publish_mappings",
        "domain_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "bulk_table_publish_mappings",
        "profile_name",
        existing_type=sa.String(200),
        nullable=False,
    )
    op.execute(
        "ALTER TABLE bulk_table_publish_mappings "
        "DROP CONSTRAINT bulk_table_publish_mappings_pkey"
    )
    op.drop_column("bulk_table_publish_mappings", "id")
    op.execute("DROP SEQUENCE IF EXISTS bulk_table_publish_mappings_id_seq")
    op.create_primary_key(
        "bulk_table_publish_mappings_pkey",
        "bulk_table_publish_mappings",
        ["table_id", "domain_id", "profile_name"],
    )

    # 2) bulk_publish_runs reverse.
    op.drop_constraint(
        "fk_bulk_publish_runs_profile_column_id",
        "bulk_publish_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_bulk_publish_runs_domain_column_id",
        "bulk_publish_runs",
        type_="foreignkey",
    )
    op.drop_column("bulk_publish_runs", "profile_column_id")
    op.drop_column("bulk_publish_runs", "domain_column_id")
    op.drop_column("bulk_publish_runs", "mode")

    # 1) Drop domain.name UNIQUE. Renames are not reversed (no record of the
    # original duplicates).
    op.drop_constraint("uq_domains_name", "domains", type_="unique")
