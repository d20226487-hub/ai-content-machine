"""Dashboard aggregation schemas.

The ``activity`` feed is an ON-DEMAND snapshot (never polled) of every
background job across ALL users that is currently queued, running, or paused —
so anyone can open the dashboard and see what the whole system is working on.
"""
from datetime import datetime

from pydantic import BaseModel


class ActivityItem(BaseModel):
    """One in-flight background run, normalised across the ~11 job types."""

    # Machine kind ('autotool' | 'generation' | 'publish' | 'gdocs_import' |
    # 'domain_cache' | 'language_sync' | 'link_check' | 'link_fix' |
    # 'structure_format' | 'csv_export' | 'backup'). The client maps it to a
    # friendly, localised label.
    kind: str
    id: int
    # What the run is about (table name, run name, action, filename…); may be
    # empty when the job has no natural label (the client then shows the kind).
    label: str = ""
    # Owner display name (full name or email); null for system jobs (backups).
    owner: str | None = None
    status: str  # 'queued' | 'running' | 'paused'
    # Progress, when the job exposes it: done of total. Either may be null.
    done: int | None = None
    total: int | None = None
    started_at: datetime | None = None
    created_at: datetime | None = None
    # In-app path to the run's detail page, or null when it has none.
    detail_path: str | None = None


class ActivityResponse(BaseModel):
    items: list[ActivityItem]
    # When the server built this snapshot (UTC). The client shows "checked at …".
    checked_at: datetime
