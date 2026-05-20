from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DomainFolder(Base):
    """A node in the Drive-style folder tree on /publish/domains.

    Mirrors `Category` (prompts) — self-referencing `parent_id`,
    null = top-level. Empty-folder enforcement lives in the API layer
    (`DELETE` refuses non-empty); the FK to self uses `ON DELETE
    RESTRICT` as belt-and-braces.

    See migration 0027 for the FK choices and the
    `domains.folder_id ON DELETE SET NULL` companion policy.
    """

    __tablename__ = "domain_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("domain_folders.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
