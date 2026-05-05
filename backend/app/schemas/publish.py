from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "posting", "posted", "failed"]
SourceKind = Literal["single", "bulk_row"]
BulkRunStatus = Literal[
    "queued", "running", "paused", "cancelled", "done", "failed"
]
RowFilter = Literal["all", "selected", "range"]
CellFilter = Literal["all", "unpublished", "failed"]


class BulkPublishRequest(BaseModel):
    table_id: int
    domain_id: int
    profile_name: str | None = None  # WP only; '' or omitted for Custom
    language: str | None = None

    row_filter: RowFilter = "all"
    selection: dict[str, Any] | None = None  # {row_ids:[...]} or {start,end}
    cell_filter: CellFilter = "all"

    field_to_column: dict[str, int] = Field(default_factory=dict)
    back_fill: dict[str, int] = Field(default_factory=dict)

    save_mapping: bool = True


class BulkRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    table_id: int
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


class BulkRunDetail(BulkRunSummary):
    row_filter: RowFilter
    selection: dict[str, Any] | None
    cell_filter: CellFilter
    field_to_column: dict[str, int]
    back_fill: dict[str, int]


class BulkRunListResponse(BaseModel):
    items: list[BulkRunSummary]
    total: int
    page: int
    page_size: int


class PublishMapping(BaseModel):
    field_to_column: dict[str, int] = Field(default_factory=dict)
    back_fill: dict[str, int] = Field(default_factory=dict)
    language: str | None = None


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
