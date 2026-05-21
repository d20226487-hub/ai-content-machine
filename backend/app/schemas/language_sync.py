"""Request / response models for the multi-domain language-sync endpoint
plus the run-history list / detail shapes.

The trigger endpoint is fed a list of ``(domain_name, languages)`` targets
— usually derived client-side from a Multi-mode bulk-publish table's
domain + language columns, or from the standalone "Run new sync" form on
the languages page. The backend resolves each name to a domain row, posts
to ``{base_url}/index.php?__add_language=1`` in parallel, AND persists the
outcome as a `LanguageSyncRun` + N `LanguageSyncResult` rows for later
reporting.

Response shape is per-target so the UI can show ✓ / ✗ next to each site
on the trigger, and the run-detail page can render the same shape later.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LanguageSyncTarget(BaseModel):
    """One row of the request — a single site + the languages it should
    have on file. Names are resolved server-side against ``Domain.name``
    (exact match, case-sensitive — same convention as the Multi-mode
    publish path uses for domain-column lookup)."""

    domain_name: str = Field(..., min_length=1, max_length=200)
    # We accept anything truthy and dedupe / normalize server-side, so a
    # caller can pass duplicates from a bulk-table column without worrying.
    languages: list[str] = Field(..., min_length=1)


class LanguageSyncRequest(BaseModel):
    targets: list[LanguageSyncTarget] = Field(..., min_length=1, max_length=200)
    # Short label for where this sync was triggered from. Stored on the
    # run so the history listing can tell "pre-flight before a publish"
    # apart from "ad-hoc fleet management". Free-form but the UI uses
    # `bulk_modal` and `standalone` today.
    source: str = Field(default="bulk_modal", max_length=40)


class LanguageSyncResolveRequest(BaseModel):
    """Pre-import validation: caller posts a list of domain names; we
    return the same list split into known + unknown. Used by the CSV
    import modal to hard-fail before the user commits a 100-row batch
    that references a typoed domain.
    """

    names: list[str] = Field(..., min_length=1, max_length=500)


class LanguageSyncResolveKnownDomain(BaseModel):
    """The minimum shape the import modal needs to populate the form's
    picked-chips state: id (for state keys), name (for display + send),
    and has_credentials (so the chip can be rendered greyed-out if the
    site has no creds). cms_type carried along for consistency with the
    main picker, but the resolve endpoint only returns Custom CMS rows."""

    id: int
    name: str
    has_credentials: bool
    cms_type: str


class LanguageSyncResolveResult(BaseModel):
    known: list[LanguageSyncResolveKnownDomain]
    unknown: list[str]


class LanguageSyncOneResult(BaseModel):
    """Outcome for one target. ``ok=True`` means the site returned 2xx;
    ``skipped`` means we never tried (unknown domain, wrong CMS type,
    missing credentials). The two are split because skip != error — the
    UI should treat them differently."""

    domain_name: str
    domain_id: int | None = None
    ok: bool
    skipped: bool = False
    skip_reason: str | None = None
    status_code: int | None = None
    # Truncated upstream response body / error message for the UI to show.
    detail: str | None = None
    elapsed_ms: int | None = None


class LanguageSyncResult(BaseModel):
    # `run_id` is the new persistent-run pointer — the trigger UI uses it
    # to deep-link "View this run" into the history page after a sync.
    run_id: int
    results: list[LanguageSyncOneResult]


# ---------- run-history list + detail ----------


class LanguageSyncRunRead(BaseModel):
    """Summary row for the history listing page — one per batch.

    Counts are denormalized on the run row at write time so the listing
    doesn't have to GROUP BY across the results table per page.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    created_by_id: int | None = None
    created_by_name: str | None = None
    source: str
    total_count: int
    ok_count: int
    fail_count: int
    skip_count: int


class LanguageSyncRunListResponse(BaseModel):
    items: list[LanguageSyncRunRead]
    total: int
    page: int
    page_size: int


class LanguageSyncResultRead(BaseModel):
    """One persisted (run, domain) outcome — same fields as
    ``LanguageSyncOneResult`` but with a created_at for the detail page.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    domain_id: int | None = None
    domain_name: str
    languages: list[str]
    ok: bool
    skipped: bool
    skip_reason: str | None = None
    status_code: int | None = None
    detail: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime


class LanguageSyncRunDetail(BaseModel):
    """Run-detail response. Carries the summary + the full result list,
    sized to a typical batch (a few dozen sites at most) so we don't
    bother paginating the results within a run."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    created_by_id: int | None = None
    created_by_name: str | None = None
    source: str
    total_count: int
    ok_count: int
    fail_count: int
    skip_count: int
    results: list[LanguageSyncResultRead]
