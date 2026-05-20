from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.ssrf import UnsafeUrlError, validate_public_url

CmsType = Literal["wordpress", "custom"]
AuthType = Literal["wp_app_password", "bearer", "api_key_header", "basic_auth"]
MultilingualPlugin = Literal["none", "polylang", "wpml"]


WpFieldType = Literal[
    "text", "textarea", "select", "taxonomy_ids", "media_url"
]


class WpField(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=200)
    type: WpFieldType = "text"
    required: bool = False
    options: list[str] | None = None
    is_meta: bool = False
    meta_key: str | None = Field(None, max_length=200)
    taxonomy: str | None = Field(None, max_length=100)


class PublishProfile(BaseModel):
    """One named publish recipe (e.g. "Standard post", "Event")."""

    name: str = Field(..., min_length=1, max_length=200)
    post_type: str = Field("posts", min_length=1, max_length=100)
    fields: list[WpField] = Field(default_factory=list)


class PublishConfig(BaseModel):
    """Per-WP-domain publish form definition.

    Stored shape: ``{"profiles": [...]}``. The legacy single-config shape
    ``{"post_type": "posts", "fields": [...]}`` is auto-promoted on read by
    :func:`normalize_publish_config`, so callers always see ``profiles``.
    """

    profiles: list[PublishProfile] = Field(default_factory=list)


def normalize_publish_config(raw: dict | None) -> dict | None:
    """Promote legacy ``{post_type, fields}`` shape to ``{profiles: [...]}``.

    Returns the raw dict otherwise. Returns None for None input.
    """
    if not raw:
        return raw
    if "profiles" in raw and isinstance(raw["profiles"], list):
        return raw
    if "post_type" in raw or "fields" in raw:
        return {
            "profiles": [
                {
                    "name": "Default",
                    "post_type": raw.get("post_type") or "posts",
                    "fields": raw.get("fields") or [],
                }
            ]
        }
    return raw


def default_wp_profiles() -> dict:
    """Default ``publish_config`` for a freshly added WordPress site.

    Seeds two standard profiles — Post and Page — so a user can publish
    immediately after import without having to define a profile by hand.
    Categories/tags are exposed as ``taxonomy_ids`` fields on the Post
    profile; bulk-creating taxonomy terms themselves is not in scope.
    Featured image is a ``media_url`` field: a numeric WP media ID is
    used directly, a URL is downloaded and uploaded to WP first.

    Users are free to delete, rename, or edit any of these from the
    domain edit modal — the seed only runs on create when no
    ``publish_config`` was supplied.
    """
    status_options = ["publish", "draft", "pending", "private"]
    return {
        "profiles": [
            {
                "name": "Post",
                "post_type": "posts",
                "fields": [
                    {"key": "title", "label": "Title", "type": "text", "required": True},
                    {"key": "content", "label": "Content", "type": "textarea", "required": True},
                    {"key": "excerpt", "label": "Excerpt", "type": "textarea"},
                    {"key": "slug", "label": "Slug", "type": "text"},
                    {
                        "key": "status",
                        "label": "Status",
                        "type": "select",
                        "options": status_options,
                        "required": True,
                    },
                    {"key": "categories", "label": "Categories", "type": "taxonomy_ids", "taxonomy": "categories"},
                    {"key": "tags", "label": "Tags", "type": "taxonomy_ids", "taxonomy": "tags"},
                    {"key": "featured_media", "label": "Featured image", "type": "media_url"},
                ],
            },
            {
                "name": "Page",
                "post_type": "pages",
                "fields": [
                    {"key": "title", "label": "Title", "type": "text", "required": True},
                    {"key": "content", "label": "Content", "type": "textarea", "required": True},
                    {"key": "excerpt", "label": "Excerpt", "type": "textarea"},
                    {"key": "slug", "label": "Slug", "type": "text"},
                    {
                        "key": "status",
                        "label": "Status",
                        "type": "select",
                        "options": status_options,
                        "required": True,
                    },
                    {"key": "featured_media", "label": "Featured image", "type": "media_url"},
                ],
            },
        ]
    }


def _has_profiles(raw: dict | None) -> bool:
    """True when ``raw`` already carries at least one profile (new or legacy shape)."""
    if not raw:
        return False
    profiles = raw.get("profiles")
    if isinstance(profiles, list) and profiles:
        return True
    # Legacy single-config shape counts too — normalize_publish_config will
    # promote it into a single profile, so we don't want to clobber it.
    if raw.get("post_type") or raw.get("fields"):
        return True
    return False


class CustomConfig(BaseModel):
    """Per-domain configuration for cms_type='custom'.

    body_template uses {{placeholder}} substitution at publish time.
    response_id_path and response_url_path are simple dot-paths into the
    JSON response (e.g. "data.id").
    """

    endpoint_path: str = Field(..., min_length=1, max_length=500)
    body_template: dict[str, Any] = Field(default_factory=dict)
    response_id_path: str | None = Field(None, max_length=200)
    response_url_path: str | None = Field(None, max_length=200)
    test_endpoint_path: str | None = Field(None, max_length=500)


class DomainBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    base_url: str = Field(..., min_length=1, max_length=500)
    cms_type: CmsType
    auth_type: AuthType
    languages: list[str] = Field(default_factory=list)
    multilingual_plugin: MultilingualPlugin = "none"
    custom_config: CustomConfig | None = None
    publish_config: PublishConfig | None = None

    # Rate-limit overrides — None means "use global default".
    requests_per_minute: int | None = Field(None, ge=1, le=100000)
    max_concurrency: int | None = Field(None, ge=1, le=1000)
    inter_request_delay_ms: int | None = Field(None, ge=0, le=600000)
    retry_max_attempts: int | None = Field(None, ge=0, le=20)
    backoff_base_ms: int | None = Field(None, ge=0, le=600000)
    backoff_jitter_ms: int | None = Field(None, ge=0, le=600000)
    respect_retry_after: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        v = v.rstrip("/")
        try:
            validate_public_url(v)
        except UnsafeUrlError as e:
            raise ValueError(f"base_url not allowed: {e}") from e
        return v

    @field_validator("languages")
    @classmethod
    def _normalize_languages(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in v:
            code = raw.strip().lower()
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        if not out:
            out = ["en"]
        return out


class DomainCreate(DomainBase):
    # Plaintext on the wire; stored Fernet-encrypted.
    # WP: "user:application_password". Bearer: the token.
    # api_key_header: JSON dict serialized as a string {"header": "X-Foo", "value": "..."}.
    credentials: str | None = None


class DomainUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    base_url: str | None = Field(None, min_length=1, max_length=500)

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("base_url must start with http:// or https://")
        v = v.rstrip("/")
        try:
            validate_public_url(v)
        except UnsafeUrlError as e:
            raise ValueError(f"base_url not allowed: {e}") from e
        return v

    cms_type: CmsType | None = None
    auth_type: AuthType | None = None
    credentials: str | None = None  # "" clears
    languages: list[str] | None = None
    multilingual_plugin: MultilingualPlugin | None = None
    custom_config: CustomConfig | None = None
    publish_config: PublishConfig | None = None
    requests_per_minute: int | None = Field(None, ge=1, le=100000)
    max_concurrency: int | None = Field(None, ge=1, le=1000)
    inter_request_delay_ms: int | None = Field(None, ge=0, le=600000)
    retry_max_attempts: int | None = Field(None, ge=0, le=20)
    backoff_base_ms: int | None = Field(None, ge=0, le=600000)
    backoff_jitter_ms: int | None = Field(None, ge=0, le=600000)
    respect_retry_after: bool | None = None


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    cms_type: CmsType
    auth_type: AuthType
    has_credentials: bool
    languages: list[str]
    multilingual_plugin: MultilingualPlugin
    custom_config: CustomConfig | None
    publish_config: PublishConfig | None
    requests_per_minute: int | None
    max_concurrency: int | None
    inter_request_delay_ms: int | None
    retry_max_attempts: int | None
    backoff_base_ms: int | None
    backoff_jitter_ms: int | None
    respect_retry_after: bool | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    # Populated only on rows returned from /domains/trash. Null on the
    # normal /domains list.
    deleted_at: datetime | None = None


class TrashBulkIds(BaseModel):
    """Body for /domains/trash/bulk-restore and /domains/trash/bulk."""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


class TestConnectionResult(BaseModel):
    ok: bool
    status_code: int | None = None
    detail: str
    elapsed_ms: int | None = None


class CsvImportResult(BaseModel):
    inserted: int
    skipped: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class DomainPickerItem(BaseModel):
    """Lite shape for the domain picker — used by the bulk + single publish
    modal comboboxes when the user has thousands of domains.

    Deliberately omits the heavy ``publish_config`` and ``custom_config``
    JSONB blobs (those are 1–2 KB per row for a typical 8-field WP
    profile). The picker only needs enough to render a result row and
    decide which entries are credentialled; the full ``Domain`` is
    fetched on demand via the existing ``GET /domains/{id}`` after the
    user actually selects something.

    ``languages`` is included because the modal derives the per-domain
    Language picker from it; it's small (handful of short strings).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    cms_type: CmsType
    has_credentials: bool
    languages: list[str]


class DomainPickerResponse(BaseModel):
    """Paginated envelope. ``has_more`` lets the combobox decide whether
    to fetch the next page (no need to expose total when we don't need to
    render a page-N-of-M control)."""

    items: list[DomainPickerItem]
    total: int
    page: int
    page_size: int
    has_more: bool
