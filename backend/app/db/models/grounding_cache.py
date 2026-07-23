"""Memoized grounded generations — see migration 0068.

A grounded provider call is billable (the Google Search tool carries a
per-request surcharge), so its result is cached keyed by a hash of the rendered
prompt + model + grounding source. An identical re-run reuses the row and pays
nothing. Rows past the service TTL are ignored and swept, so the table is a pure
cache — safe to truncate at any time.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroundingCache(Base):
    __tablename__ = "grounding_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # SHA-256 hex of rendered_prompt + model + grounding_source.
    cache_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    finish_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The distilled {queries, sources} the grounded call cited (may be null).
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
