from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BackupRun(Base):
    """One row per pg_dump invocation. Surfaced in the admin Settings page.

    `status` values: 'running' | 'ok' | 'failed'.
    `trigger` values: 'manual' | 'scheduled'.
    """

    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
