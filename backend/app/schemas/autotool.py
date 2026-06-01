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


class AutotoolPostPreview(BaseModel):
    """The POST request that would be sent to ImportPosts for one table.

    Step 2 (actual sending) isn't built yet, so this is a faithful preview.
    ``site_column_id`` is the column whose distinct values fill ``body.sites``
    — auto-detected by default, remappable via the ``site_column_id`` query
    param. The X-Api-Key header is masked (the real key is never returned).
    """

    method: str = "POST"
    url: str | None = None
    headers: dict[str, str]
    body: dict[str, Any]
    columns: list[ColumnRef] = []
    site_column_id: int | None = None
    detected_site_column_id: int | None = None
    site_count: int = 0
    target_configured: bool = False
    api_key_configured: bool = False
