"""Schemas for bulk Custom-CMS cache-clear runs.

A run targets a set of domains by id + an action; only Custom-CMS domains
become items (WordPress publishes via Autotool and has no cache endpoints).
See app/services/domain_cache.py and app/db/models/domain_cache.py.
"""
from datetime import datetime

from pydantic import BaseModel, field_validator

# Mirrors the runaway guard in the service so the API rejects oversized
# selections before doing any work.
MAX_CACHE_RUN_DOMAINS = 5000

# Only 'clear' can be created now — warming was removed because it overloaded
# sites under bulk runs. Historical runs may still carry 'warm' /
# 'clear_and_warm' in the DB, so the READ schemas below keep ``action`` a plain
# str (they don't validate against this set).
_ACTIONS = {"clear"}


class DomainCacheRunCreate(BaseModel):
    domain_ids: list[int]
    # Always 'clear' (warm removed). Defaulted so callers can omit it.
    action: str = "clear"

    @field_validator("action")
    @classmethod
    def _check_action(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in _ACTIONS:
            raise ValueError(f"action must be one of {sorted(_ACTIONS)}")
        return v

    @field_validator("domain_ids")
    @classmethod
    def _check_ids(cls, v: list[int]) -> list[int]:
        # De-dupe while preserving order; reject empty / oversized up front.
        seen: set[int] = set()
        out: list[int] = []
        for i in v:
            if i not in seen:
                seen.add(i)
                out.append(i)
        if not out:
            raise ValueError("Select at least one domain.")
        if len(out) > MAX_CACHE_RUN_DOMAINS:
            raise ValueError(
                f"Too many domains ({len(out)}) for one run "
                f"(max {MAX_CACHE_RUN_DOMAINS})."
            )
        return out


class DomainCacheRunItemRead(BaseModel):
    """One domain within a run."""

    id: int
    domain_id: int | None = None
    domain_name: str
    base_url: str
    status: str  # 'queued' | 'running' | 'done' | 'failed' | 'skipped'
    clear_status_code: int | None = None
    warm_status_code: int | None = None
    detail: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime


class DomainCacheRunRead(BaseModel):
    """A run, as shown in the list."""

    id: int
    action: str  # 'clear' | 'warm' | 'clear_and_warm'
    status: str  # 'queued' | 'running' | 'cancelled' | 'done' | 'failed'
    total: int
    done: int
    failed: int
    skipped: int = 0
    skipped_unsupported: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DomainCacheRunsPage(BaseModel):
    items: list[DomainCacheRunRead]
    total: int
    page: int
    page_size: int


class DomainCacheRunDetail(DomainCacheRunRead):
    """A run plus a page of its items (the progress page)."""

    error: str | None = None
    items: list[DomainCacheRunItemRead] = []
    items_total: int = 0
    items_page: int = 1
    items_page_size: int = 50
