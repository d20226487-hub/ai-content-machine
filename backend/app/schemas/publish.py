from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JobStatus = Literal["queued", "posting", "posted", "failed"]
SourceKind = Literal["single", "bulk_row"]
BulkRunStatus = Literal[
    "queued", "running", "paused", "cancelled", "done", "failed"
]
RowFilter = Literal["all", "selected", "range"]
CellFilter = Literal["all", "unpublished", "failed"]
PublishMode = Literal["single", "multi"]


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

    language: str | None = None

    row_filter: RowFilter = "all"
    selection: dict[str, Any] | None = None  # {row_ids:[...]} or {start,end}
    cell_filter: CellFilter = "all"

    field_to_column: dict[str, int] = Field(default_factory=dict)
    back_fill: dict[str, int] = Field(default_factory=dict)

    save_mapping: bool = True

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
