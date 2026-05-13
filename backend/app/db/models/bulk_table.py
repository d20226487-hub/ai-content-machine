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
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class BulkTableFolder(Base, TimestampMixin):
    """Flat folder for organizing bulk tables. No nesting — folder_id on
    bulk_tables is the only relationship; subfolders aren't supported in v1."""

    __tablename__ = "bulk_table_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
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
