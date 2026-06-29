"""Schemas for background CSV export jobs (see app/db/models/csv_export.py)."""
from datetime import datetime

from pydantic import BaseModel


class CsvExportJobRead(BaseModel):
    id: int
    table_id: int | None = None
    table_name: str
    filename: str
    status: str  # 'queued' | 'running' | 'done' | 'failed'
    rows_total: int
    rows_done: int
    byte_size: int | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
