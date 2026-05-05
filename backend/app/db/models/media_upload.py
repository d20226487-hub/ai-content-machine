from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MediaUpload(Base):
    """Cache: (domain, source_url) → wp_media_id.

    Avoids re-uploading the same image when many bulk rows reference it.
    No TTL in v1; admins can clear the cache per-domain via the API.
    """

    __tablename__ = "media_uploads"

    domain_id: Mapped[int] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True
    )
    source_url: Mapped[str] = mapped_column(String(2000), primary_key=True)
    wp_media_id: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
