from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Stable identifier used by the application (e.g. 'ai_studio'). Not user-editable.
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    default_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_creation_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # JSON array of strings: e.g. ["gemini-2.5-pro", "gemini-2.5-flash"]
    available_models: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # --- Rate limit / batching knobs ---
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    inter_request_delay_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    backoff_base_ms: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    backoff_jitter_ms: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    respect_retry_after: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    @property
    def has_extra_config(self) -> bool:
        return bool(self.extra_config_encrypted)
