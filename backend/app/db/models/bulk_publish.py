from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkPublishRun(Base):
    """A single bulk-publish operation: one table → one (domain, profile)."""

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
    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )
    # '' for Custom CMS (no profile concept). Real profile name for WP.
    profile_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
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
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class BulkTablePublishMapping(Base):
    """Memo of the most-recent column→field mapping per (table, domain, profile).

    The BulkPublishModal pre-fills from this row; users can clear it via the
    DELETE endpoint to start fresh.
    """

    __tablename__ = "bulk_table_publish_mappings"

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), primary_key=True
    )
    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True
    )
    profile_name: Mapped[str] = mapped_column(
        String(200), primary_key=True, default=""
    )

    field_to_column: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    back_fill: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
