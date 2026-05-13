from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.models.role import Role


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Uniqueness enforced via the partial index uq_users_email_active
    # (migration 0025) — only active rows participate, so a trashed user
    # can hold an email that a new active user now uses.
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")

    # NULL = active, non-NULL = trashed. `get_current_user` filters
    # `deleted_at IS NULL` so a trashed user's existing JWT is rejected
    # on the next request (matches the old hard-delete kick-out).
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
