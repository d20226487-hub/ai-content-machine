"""Bulk-mode generation tables.

Four tables:
  bulk_tables       — the table itself, owned by a user
  bulk_table_columns — schema (name, position, kind, prompt assignment)
  bulk_table_rows   — explicit rows so reorder/delete is cheap (no row_index shifting)
  bulk_table_cells  — sparse: only created when a value exists. Unique per (row, column).

Output columns can carry a prompt_id + variable_map (JSON dict mapping each
prompt variable name to the column id whose value should fill it). This is
stored now; AI generation that consumes it lands in Step C.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class BulkTableFolder(Base, TimestampMixin):
    """A node in the Library folder tree.

    Self-referencing ``parent_id`` (null = top level) lets folders nest, same
    shape as ``DomainFolder`` (migration 0027 / 0056). ``bulk_tables.folder_id``
    still assigns each table to exactly one folder. Empty-folder enforcement
    (no child folders, no live tables) lives in the API DELETE; the self-FK is
    ON DELETE RESTRICT as belt-and-braces.
    """

    __tablename__ = "bulk_table_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("bulk_table_folders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class BulkTable(Base, TimestampMixin):
    __tablename__ = "bulk_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("bulk_table_folders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # NULL = active. Non-NULL = trashed (soft-deleted). All "normal" endpoints
    # filter `deleted_at IS NULL`; the /library/trash surface is the only
    # place trashed rows are reachable.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Autotool (3rd publishing mode) -----
    # When enabled, the table is exposed as a CSV at an unauthenticated,
    # unguessable URL (/autotool/<token>.csv) so the external Autotool proxy
    # can fetch it and push the content to target sites. Disabling clears the
    # token, so the public link dies immediately. See migration 0043.
    autotool_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    autotool_token: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True
    )

    # ----- Google-Docs import provenance -----
    # For tables built by the Google-Docs importer: the planned page list per
    # site, shape [{"domain": str, "language": str, "structure": [str, ...]}].
    # Drives the "Site structure" reference panel below the grid (and is there
    # for the operator to supply to AI). NULL for tables not built that way.
    # See migration 0050.
    gdocs_structure: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Per-row slug audit for Google-Docs imports: what the AI pairing did to
    # each row's slug — shape [{"row","domain","language","seo_title","anchor"
    # (raw "before"),"slug" (final "after"),"changed","unmatched"}]. Drives the
    # "AI slug mapping" panel. NULL for non-imported tables. See migration 0051.
    gdocs_slug_audit: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    columns: Mapped[list["BulkTableColumn"]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        order_by="BulkTableColumn.position",
    )
    rows: Mapped[list["BulkTableRow"]] = relationship(
        back_populates="table",
        cascade="all, delete-orphan",
        order_by="BulkTableRow.position",
    )


class BulkTableColumn(Base):
    __tablename__ = "bulk_table_columns"
    __table_args__ = (
        # Prevents two concurrent column-add requests from landing on the same
        # position. Without this, both could pre-compute the same `max+1`,
        # both INSERT, and end up with duplicate positions for the table.
        UniqueConstraint("table_id", "position", name="uq_bulk_columns_table_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 'input' (user types data) | 'output' (AI fills based on prompt + variable_map)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="input")

    prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True
    )
    # null = "always use the prompt's current version at generation time"
    prompt_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON: { "tone": <column_id>, "topic": <column_id>, ... }
    variable_map: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Per-column overrides; null = fall back to first enabled provider / its default model.
    provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    table: Mapped[BulkTable] = relationship(back_populates="columns")


class BulkTableRow(Base):
    __tablename__ = "bulk_table_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    table: Mapped[BulkTable] = relationship(back_populates="rows")


class BulkTableCell(Base):
    __tablename__ = "bulk_table_cells"
    __table_args__ = (
        UniqueConstraint("row_id", "column_id", name="uq_bulk_cells_row_column"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    row_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_table_rows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_table_columns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'empty' | 'manual' (user-typed) | 'generating' | 'generated' | 'failed'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="empty")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(120), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Back-link to the bulk_generation_runs row that scheduled this
    # cell. NULL for cells generated before migration 0030 or for
    # cells written via the inline edit / non-batch paths. ON DELETE
    # SET NULL on the FK so a finished run can be hard-deleted without
    # taking the cell's content with it.
    generation_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("bulk_generation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # On-demand translations memoized per language. Shape:
    #   { "ru": { "text": ..., "provider_used": ..., "model_used": ...,
    #             "translated_at": "<ISO 8601>" }, ... }
    # NULL when no translation has ever been requested. Cleared by the
    # upsert path and the bulk-generation worker when the underlying
    # `value` changes, so a stale translation never outlives its source.
    translations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
