from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PublishJob(Base):
    """A single publish attempt to a domain.

    Phase 2 only writes rows with source_kind='single'. Phase 3 will add
    'bulk_cell' / 'bulk_row' for the table-driven publish flow.
    """

    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    domain_id: Mapped[int | None] = mapped_column(
        ForeignKey("domains.id", ondelete="SET NULL"), nullable=True
    )

    # 'single' (Phase 2) | 'bulk_cell' (Phase 3+)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # e.g. {"generation_id": 5, "prompt_id": 3}
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 'queued' | 'posting' | 'posted' | 'failed'
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # Language code chosen at publish time (e.g. 'en', 'de').
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)

    payload_sent: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    cms_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cms_post_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    profile_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Upstream HTTP status code as returned by the CMS. Nullable: rows
    # that landed before migration 0026 have NULL here and we don't
    # backfill (the code is only present in error text for failures, and
    # only inferable as 2xx for posted rows). The PublishJobRead schema
    # surfaces this directly so the run-detail UI can show "HTTP 201"
    # next to "posted" without parsing the error string.
    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
