"""FindReplaceRun — a revertable bulk find-and-replace applied to a table.

Only *Replace* creates a row here; plain *Find* is read-only and persists
nothing. Each run captures a full before/after ``snapshot`` so the operation
can be reverted in one click — revert simply re-writes the old values back
through the normal cell path. Runs are kept indefinitely (persistent
history) and CASCADE-deleted when their table is hard-deleted.

See migration 0033 for the table layout.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FindReplaceRun(Base):
    __tablename__ = "find_replace_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    table_id: Mapped[int] = mapped_column(
        ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The search/replace configuration, kept so the history list and run
    # detail page can show "what was run" without re-deriving it.
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    replacement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_regex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whole_cell: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # List[int] of column ids the run targeted (empty = all columns).
    column_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Total occurrences replaced (whole_cell counts 1 per cell).
    match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
