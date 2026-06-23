"""Schemas for the Autotool connection config (3rd publishing mode).

A singleton config (stored in app_settings under "autotool_config") holding the
target ImportPosts endpoint + the X-Api-Key used to authenticate to the
external Autotool proxy. The key is Fernet-encrypted at rest and never returned
to the client — the read schema only signals whether one is set.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AutotoolConfigRead(BaseModel):
    """Masked view: the API key is never echoed back."""

    target_url: str | None = None
    api_key_configured: bool = False


class AutotoolConfigUpdate(BaseModel):
    """Partial update.

    Field semantics mirror the backup S3 secret pattern:
      * omitted / None  → leave unchanged
      * "" (empty)      → clear
      * non-empty       → set
    """

    target_url: str | None = None
    api_key: str | None = None


class AutotoolTestResult(BaseModel):
    """Same shape domains use for Test connection."""

    ok: bool
    status_code: int | None = None
    detail: str
    elapsed_ms: int | None = None


# ----- shared tables + POST request preview -----


class AutotoolTableItem(BaseModel):
    id: int
    name: str
    autotool_token: str | None = None
    csv_path: str | None = None
    row_count: int = 0
    column_count: int = 0
    updated_at: datetime


class AutotoolTablesPage(BaseModel):
    items: list[AutotoolTableItem]
    total: int
    page: int
    page_size: int


class ColumnRef(BaseModel):
    id: int
    name: str


class AutotoolDomainRequest(BaseModel):
    """One ImportPosts POST — a single ``PAGE_SIZE``-row page for one site.

    A domain with more rows than the page size produces several of these, one
    per ``start`` offset. ``total`` is the domain's full row count (so the
    importer can tell when it has reached the last page); ``row_count`` is the
    rows in THIS page.
    """

    site: str
    file: str
    csv_path: str
    start: int
    total: int
    row_count: int
    body: dict[str, Any]


class AutotoolPostPreview(BaseModel):
    """The POST requests that would be sent to ImportPosts for one table.

    The table is split by its site column into ONE request per distinct domain
    (Autotool needs one file per site). ``site_column_id`` is auto-detected by
    default and remappable via the query param. Shared ``headers`` carry a
    masked X-Api-Key (the real key is never returned). Step 2 (actual sending)
    isn't built yet, so this is a faithful preview.
    """

    method: str = "POST"
    url: str | None = None
    headers: dict[str, str]
    columns: list[ColumnRef] = []
    site_column_id: int | None = None
    detected_site_column_id: int | None = None
    page_size: int = 50
    domain_count: int = 0
    page_count: int = 0
    total_rows_matched: int = 0
    table_row_count: int = 0
    requests: list[AutotoolDomainRequest] = []
    target_configured: bool = False
    api_key_configured: bool = False


# ----- send runs (background, with a progress page) -----


class AutotoolRunCreate(BaseModel):
    table_id: int
    site_column_id: int | None = None
    page_size: int | None = None


class AutotoolRunItemRead(BaseModel):
    """One ImportPosts POST within a run — a single (domain, page)."""

    id: int
    site: str
    start: int
    total: int
    status: str  # 'queued' | 'sending' | 'sent' | 'failed' | 'skipped'
    external_id: Any | None = None  # the proxy id for this item's site
    status_code: int | None = None
    detail: str | None = None
    response_snippet: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime


class AutotoolRunRead(BaseModel):
    """A run, as shown in the list."""

    id: int
    table_id: int | None = None
    table_name: str
    target_url: str
    page_size: int
    status: str  # 'queued' | 'running' | 'cancelled' | 'done' | 'failed'
    total: int
    sent: int
    failed: int
    skipped: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AutotoolRunsPage(BaseModel):
    items: list[AutotoolRunRead]
    total: int
    page: int
    page_size: int


class AutotoolRunDetail(AutotoolRunRead):
    """A run plus a page of its items (the progress page)."""

    site_column_id: int | None = None
    error: str | None = None
    items: list[AutotoolRunItemRead] = []
    items_total: int = 0
    items_page: int = 1
    items_page_size: int = 50
