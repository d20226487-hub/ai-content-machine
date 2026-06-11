"""NormalizeRun — a revertable bulk normalize applied to a table.

Mirrors :class:`FindReplaceRun`: applying the normalize transforms across the
chosen columns creates one row here, capturing a full before/after ``snapshot``
so the operation can be reverted in one click — revert simply re-writes the old
values back through the normal cell path. Runs are kept indefinitely (persistent
history) and CASCADE-deleted when their table is hard-deleted.

The only difference from FindReplaceRun is the find/replace-specific columns
(pattern, replacement, regex flags, match_count) are replaced by a single
``operations`` JSONB (the selected subset of the canonical transforms, in
order).

See migration 0053 for the table layout.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NormalizeRun(Base):
    __tablename__ = "normalize_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The selected transforms (subset of the canonical OPERATIONS), in order.
    # Kept so the history list + run detail can show "what was run".
    operations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # List[int] of column ids the run targeted (empty = all columns).
    column_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Distinct cells whose value changed.
    cell_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 'applied' | 'reverted'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    # Optional user-given label (NULL → UI shows a "<tool> #<id>" fallback).
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # List of {row_id, column_id, old_value, old_status, new_value}. Drives
    # the before/after table on the run page AND the one-click revert.
    snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reverted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
