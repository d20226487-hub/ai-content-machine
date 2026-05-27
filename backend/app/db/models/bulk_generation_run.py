"""BulkGenerationRun — bookkeeping for a fan-out AI generation batch.

Created the moment ``POST /library/tables/{id}/generate`` accepts a
batch; lives until the last cell finishes (or until the operator
cancels). The Celery worker consults ``status`` before processing each
cell so a Cancel click stops in-flight work without waiting for the
queue to drain naturally.

Schema mirrors ``BulkPublishRun`` deliberately so the editor UI can
reuse the same counter/progress patterns it already uses on publish
runs. See migration 0030 for the table layout.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BulkGenerationRun(Base):
    __tablename__ = "bulk_generation_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False
    )

    # Lifecycle: queued → running → (cancelled | done | failed).
    # The worker fails-loud if it sees any other value.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued"
    )

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Only populated when the run itself failed (e.g., a database issue
    # in the seed phase). Per-cell errors live on bulk_table_cells.error.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
