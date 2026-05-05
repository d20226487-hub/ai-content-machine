from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Generation(Base, TimestampMixin):
    """A user-saved Single-mode generation.

    Snapshots the prompt name + version + variables + output so the saved
    record survives even if the original prompt is later renamed or deleted.
    """

    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # FK kept for navigation (click-through to the prompt's history) but nullable
    # so prompts can be deleted without losing the saved generation.
    prompt_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    prompt_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)

    rendered_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(120), nullable=False)
    finish_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
