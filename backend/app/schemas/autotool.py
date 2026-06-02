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
    """One ImportPosts POST — for a single target site, with that site's file."""

    site: str
    file: str
    csv_path: str
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
    domain_count: int = 0
    total_rows_matched: int = 0
    table_row_count: int = 0
    requests: list[AutotoolDomainRequest] = []
    target_configured: bool = False
    api_key_configured: bool = False


# ----- firing the requests -----


class AutotoolSendItem(BaseModel):
    """Outcome of one per-domain ImportPosts POST."""

    site: str
    file: str
    ok: bool
    status_code: int | None = None
    detail: str
    response_snippet: str | None = None
    elapsed_ms: int | None = None


class AutotoolSendResult(BaseModel):
    total: int
    sent: int
    failed: int
    target_url: str | None = None
    items: list[AutotoolSendItem] = []
