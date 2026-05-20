from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JobStatus = Literal["queued", "posting", "posted", "failed", "skipped"]
SourceKind = Literal["single", "bulk_row"]
BulkRunStatus = Literal[
    "queued", "running", "paused", "cancelled", "done", "failed"
]
RowFilter = Literal["all", "selected", "range"]
CellFilter = Literal["all", "unpublished", "failed"]
PublishMode = Literal["single", "multi"]
# Per-run publish operation.
#   'create' — POST a new post / page.
#   'update' — For WP: resolve an existing post via lookup_kind+lookup_column_id
#              and PATCH it. For Custom CMS: send action='update' with the
#              upstream id supplied as the `id` field-to-column mapping; no
#              find_post pre-flight (the upstream resolves the id itself).
#   'upsert' — Custom CMS only. Server-side slug → existing-page lookup with
#              fallback to create when the slug isn't found. WP has no native
#              upsert and the API rejects this combination at run creation.
PublishOperation = Literal["create", "update", "upsert"]
PublishLookupKind = Literal["id", "slug"]
# How to react when a Create row's slug already exists on the target
# (in its language, per the find_post language filter). 'create' = always
# POST (WP auto-suffixes); 'skip' = log as skipped; 'update' = PATCH the
# existing post.
OnSlugConflict = Literal["create", "skip", "update"]


class BulkPublishRequest(BaseModel):
    table_id: int
    # 'single' (today's behavior) or 'multi' (domain + profile come from
    # cells on each row).
    mode: PublishMode = "single"

    # Single-mode targets — required when mode='single', ignored otherwise.
    domain_id: int | None = None
    profile_name: str | None = None  # WP only; '' or omitted for Custom

    # Multi-mode column refs — required when mode='multi', ignored otherwise.
    domain_column_id: int | None = None
    profile_column_id: int | None = None
    # Per-row language column (multi mode only). Cell value is lowercased
    # + trimmed and matched against the resolved domain's languages.
    # Run-level `language` becomes the fallback when this column is unset
    # OR not in multi mode.
    language_column_id: int | None = None

    language: str | None = None

    row_filter: RowFilter = "all"
    selection: dict[str, Any] | None = None  # {row_ids:[...]} or {start,end}
    cell_filter: CellFilter = "all"

    field_to_column: dict[str, int] = Field(default_factory=dict)
    back_fill: dict[str, int] = Field(default_factory=dict)

    save_mapping: bool = True

    # Create vs Update. Update mode resolves each row to an existing WP post
    # via (lookup_kind, lookup_column_id) and PATCHes it instead of posting
    # a new one. WP-only — Custom CMS in update mode is rejected at run
    # creation by the API layer (it has no PATCH/find convention).
    operation: PublishOperation = "create"
    lookup_kind: PublishLookupKind | None = None
    lookup_column_id: int | None = None

    # Slug-conflict handling on Create. Pre-checks each row's slug via the
    # WP REST API and either skips a duplicate or PATCHes it. Adds one GET
    # per row, language-aware via find_post.
    on_slug_conflict: OnSlugConflict = "create"

    @model_validator(mode="after")
    def _validate_mode(self) -> "BulkPublishRequest":
        if self.mode == "single":
            if self.domain_id is None:
                raise ValueError("domain_id is required in single mode")
            # multi-only fields ignored even if sent
        else:
            if self.domain_column_id is None:
                raise ValueError("domain_column_id is required in multi mode")
            # profile_column_id required for WP; we can't validate per-CMS here
            # (need the resolved domain), so the API validates after looking
            # up domains. profile_column_id presence is checked there.

        # lookup_kind / lookup_column_id are WP-specific (find_post by id|slug).
        # Custom CMS update sends the upstream id via the `id` field-to-column
        # mapping instead — no find_post needed. We can't see cms_type at this
        # layer, so we don't enforce lookup_* presence here; the API layer
        # validates it for WP runs and the service-layer Custom-CMS branch
        # ignores those fields entirely.
        if self.on_slug_conflict != "create":
            # Skip / Update behaviors only apply to Create-mode runs. In
            # Update mode every row already targets an existing post; a
            # second pre-check is redundant and likely a UI mistake.
            if self.operation != "create":
                raise ValueError(
                    "on_slug_conflict applies only when operation='create'. "
                    "Update-mode runs already target an existing post."
                )
            # Without `slug` in field_to_column there's nothing to pre-check
            # (WP would derive the slug from the title server-side). Fail
            # explicitly so the user knows the toggle has no effect.
            if "slug" not in self.field_to_column:
                raise ValueError(
                    "on_slug_conflict requires 'slug' to be mapped in "
                    "field_to_column. Map a column to the slug field, or "
                    "set on_slug_conflict='create'."
                )
        return self


class BulkRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    table_id: int
    mode: PublishMode = "single"
    domain_id: int | None
    domain_name: str | None = None
    table_name: str | None = None
    profile_name: str | None
    language: str | None
    status: BulkRunStatus
    total: int
    done: int
    failed: int
    skipped: int
    error: str | None
    created_by_id: int | None
    operation: PublishOperation = "create"
    lookup_kind: PublishLookupKind | None = None
    lookup_column_id: int | None = None
    language_column_id: int | None = None
    on_slug_conflict: OnSlugConflict = "create"


class ByDomainStat(BaseModel):
    """Per-domain breakdown for a multi-mode run's detail view."""

    domain_id: int | None
    domain_name: str | None  # null when domain_id is null (unresolved)
    total: int
    posted: int
    failed: int


class BulkRunDetail(BulkRunSummary):
    row_filter: RowFilter
    selection: dict[str, Any] | None
    cell_filter: CellFilter
    field_to_column: dict[str, int]
    back_fill: dict[str, int]

    domain_column_id: int | None = None
    profile_column_id: int | None = None
    # Empty list for single-mode runs (UI hides the panel anyway).
    by_domain: list[ByDomainStat] = Field(default_factory=list)


class BulkRunListResponse(BaseModel):
    items: list[BulkRunSummary]
    total: int
    page: int
    page_size: int


class PublishMapping(BaseModel):
    field_to_column: dict[str, int] = Field(default_factory=dict)
    back_fill: dict[str, int] = Field(default_factory=dict)
    language: str | None = None
    # Multi-mode only: which columns held domain / profile last time. Null
    # for single-mode mappings; the UI ignores them in that case.
    domain_column_id: int | None = None
    profile_column_id: int | None = None
    language_column_id: int | None = None
    # Remembered Create/Update choice + lookup target, so the modal restores
    # the same shape next time the user opens it for this (table, mode).
    operation: PublishOperation = "create"
    lookup_kind: PublishLookupKind | None = None
    lookup_column_id: int | None = None
    on_slug_conflict: OnSlugConflict = "create"


class PublishDefaults(BaseModel):
    """Global publish rate-limit defaults. Mirrored on each domain as a nullable
    override; NULL on the domain means "use the value from here".
    """

    requests_per_minute: int = Field(..., ge=1, le=100000)
    max_concurrency: int = Field(..., ge=1, le=1000)
    inter_request_delay_ms: int = Field(..., ge=0, le=600000)
    retry_max_attempts: int = Field(..., ge=0, le=20)
    backoff_base_ms: int = Field(..., ge=0, le=600000)
    backoff_jitter_ms: int = Field(..., ge=0, le=600000)
    respect_retry_after: bool


class PublishSingleRequest(BaseModel):
    domain_id: int
    fields: dict[str, Any] = Field(default_factory=dict)
    language: str | None = None
    profile_name: str | None = None  # WP only; Custom ignores
    source_ref: dict[str, Any] | None = None  # e.g. {"generation_id": 5, "prompt_id": 3}


class PublishJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    finished_at: datetime | None
    domain_id: int | None
    domain_name: str | None = None
    source_kind: SourceKind
    source_ref: dict[str, Any] | None
    status: JobStatus
    language: str | None
    cms_post_id: str | None
    cms_post_url: str | None
    error: str | None
    warnings: list[str] | None = None
    profile_name: str | None = None
    created_by_id: int | None


class PublishJobDetail(PublishJobRead):
    payload_sent: dict[str, Any] | None
    response_json: dict[str, Any] | None


class PublishJobListResponse(BaseModel):
    items: list[PublishJobRead]
    total: int
    page: int
    page_size: int
