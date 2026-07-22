"""CellShareLink — a public, read-only link to ONE bulk-table cell's preview.

Lets someone without an ACM account read a single generated cell. The link is
LIVE: the public view always renders the cell's CURRENT value, so an edit shows
up on refresh (and, by the same token, keeps being exposed until the link
expires or is revoked).

Safety properties, all load-bearing:
  * ``token`` is unguessable (``secrets.token_urlsafe(32)``) — it IS the
    credential, so it's the only thing standing between the content and the
    internet.
  * ``expires_at`` is mandatory (30 days by default) so a forgotten link dies
    on its own; ``revoked_at`` kills it immediately.
  * The row/column FKs cascade, so deleting the cell's row or column drops the
    link too — a public URL can't outlive what it points at.

See migration 0062.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# How long a new link stays valid. Deliberately finite: a public URL that never
# expires is a slow leak.
SHARE_LINK_TTL_DAYS = 30


class CellShareLink(Base):
    __tablename__ = "cell_share_links"
    __table_args__ = (
        UniqueConstraint("token", name="uq_cell_share_links_token"),
        Index("ix_cell_share_links_cell", "table_id", "row_id", "column_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False)

    table_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bulk_tables.id", ondelete="CASCADE"), nullable=False
    )
    row_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bulk_table_rows.id", ondelete="CASCADE"), nullable=False
    )
    column_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("bulk_table_columns.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_active(self) -> bool:
        """Not revoked and not past its expiry."""
        if self.revoked_at is not None:
            return False
        return self.expires_at > datetime.now(timezone.utc)
