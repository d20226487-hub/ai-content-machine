from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkPublishRun(Base):
    """A single bulk-publish operation.

    `mode` determines how each row's target is resolved:
      * 'single' — every row goes to (domain_id, profile_name) on this run.
      * 'multi'  — each row reads its own domain + profile from cells in
        the columns referenced by domain_column_id / profile_column_id.
    """

    __tablename__ = "bulk_publish_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False
    )

    # 'single' | 'multi'
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="single"
    )

    # Single-mode targets. Null for multi-mode runs.
    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )
    # '' for Custom CMS or for multi-mode (where the profile is per-row).
    profile_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # Multi-mode targets. Null for single-mode runs.
    domain_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    profile_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    # Per-row language column (multi mode only). When set, each row's
    # language is read from this cell (lowercase + trim, must match the
    # resolved domain's `languages[]`); empty cell → row fails.
    language_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )

    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 'all' | 'selected' | 'range'
    row_filter: Mapped[str] = mapped_column(String(20), nullable=False)
    selection: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 'all' | 'unpublished' | 'failed'
    cell_filter: Mapped[str] = mapped_column(String(20), nullable=False, default="all")

    field_to_column: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    back_fill: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # 'queued'|'running'|'paused'|'cancelled'|'done'|'failed'
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Optional user-given label (NULL → UI shows a "<tool> #<id>" fallback).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 'create' (POST a new post) | 'update' (PATCH an existing post resolved
    # via lookup_kind + lookup_column_id). Default 'create' preserves v1
    # behavior for rows that predate migration 0020.
    operation: Mapped[str] = mapped_column(
        String(16), nullable=False, default="create"
    )
    # 'id' | 'slug' — only meaningful when operation='update'.
    lookup_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The bulk-table column whose cell value identifies the existing post for
    # each row. SET NULL on column delete so a missing column doesn't dangle
    # the FK; the resolver will fail per-row with a clear message.
    lookup_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )

    # What to do in Create mode when a post with the same slug (in the
    # row's target language) already exists. 'create' = always POST (WP
    # auto-suffixes), 'skip' = record as skipped, 'update' = PATCH the
    # existing post. Only meaningful when operation='create'.
    on_slug_conflict: Mapped[str] = mapped_column(
        String(16), nullable=False, default="create"
    )

    # Built-in Custom CMS page type (migration 0055). 'ordinary' uses the
    # domain's own endpoint + body_template; 'match' pins the hardcoded
    # /add-sport-page endpoint + the sport field set. Ignored for WordPress
    # rows. See app/cms/custom_page_types.py.
    custom_page_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ordinary", server_default="ordinary"
    )

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class BulkTablePublishMapping(Base):
    """Memo of the most-recent column→field mapping for one table.

    Two shapes coexist in this table — selected by the `mode` column:

    Single mode: keyed on (table_id, domain_id, profile_name). One row per
    triple. Used by the BulkPublishModal in single mode to pre-fill the
    column→field mapping when the user picks the same domain+profile they
    used last time.

    Multi mode: keyed on (table_id) only. One row per table. Holds the
    column→field mapping plus which columns hold the per-row domain and
    profile. Cross-mode reads don't collide because partial unique indexes
    in the migration enforce shape-by-mode separately.
    """

    __tablename__ = "bulk_table_publish_mappings"
    __table_args__ = (
        # Partial uniques are created in migration 0017; we declare them here
        # only for documentation. Alembic doesn't autogenerate from them.
        Index(
            "uq_btpm_single",
            "table_id",
            "domain_id",
            "profile_name",
            unique=True,
            postgresql_where="mode = 'single'",
        ),
        Index(
            "uq_btpm_multi",
            "table_id",
            unique=True,
            postgresql_where="mode = 'multi'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False
    )
    # 'single' | 'multi'
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="single"
    )

    # Single-mode key parts. Null for multi.
    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), nullable=True
    )
    profile_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Multi-mode column references. Null for single.
    domain_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    profile_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    language_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )

    field_to_column: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    back_fill: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Mirrors the same three fields on BulkPublishRun so the saved mapping
    # remembers the user's last operation + lookup choice. Modal pre-fills
    # both on open. Independent per (table, mode) — single + multi can each
    # hold their own create-vs-update memory.
    operation: Mapped[str] = mapped_column(
        String(16), nullable=False, default="create"
    )
    lookup_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    lookup_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    on_slug_conflict: Mapped[str] = mapped_column(
        String(16), nullable=False, default="create"
    )
    # Remembered Custom CMS page type (migration 0055), so the modal restores
    # the last 'ordinary' / 'match' choice for this (table, mode).
    custom_page_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ordinary", server_default="ordinary"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
