from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Domain(Base):
    """A site we can publish content to.

    Holds the connection target plus encrypted credentials. The actual
    publish call routes through `app.cms.registry.get_cms_client(domain)`.
    """

    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)

    # 'wordpress' | 'custom'
    cms_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # 'wp_app_password' (WP) | 'bearer' | 'api_key_header'
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # Fernet-encrypted. For WP app password: "user:application_password".
    # For bearer: the token. For api_key_header: JSON {"header": "...", "value": "..."}.
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # First entry is the default language. Single-element list = monolingual.
    languages: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    # 'none' | 'polylang' | 'wpml' — meaningful only for WP.
    multilingual_plugin: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none"
    )

    # Only used when cms_type='custom':
    #   {
    #     "endpoint_path": "/api/posts",
    #     "body_template": { "title": "{{title}}", ... },
    #     "response_id_path": "id",
    #     "response_url_path": "url",
    #     "test_endpoint_path": null  # optional, future
    #   }
    custom_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Per-domain rate-limit overrides. NULL means "use global default from
    # app_settings". Resolved at runtime by services/publish_rate_limit.py.
    requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inter_request_delay_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backoff_base_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backoff_jitter_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    respect_retry_after: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Only used when cms_type='wordpress':
    #   {
    #     "post_type": "posts",
    #     "fields": [
    #       {"key": "title", "label": "Title", "type": "text", "required": true},
    #       {"key": "subtitle", "label": "Subtitle", "type": "text",
    #        "is_meta": true, "meta_key": "acf_subtitle"},
    #       ...
    #     ]
    #   }
    publish_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def has_credentials(self) -> bool:
        return bool(self.credentials_encrypted)
