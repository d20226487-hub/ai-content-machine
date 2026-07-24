"""Schemas for the AI Helper bulk-table mini-tool."""
from datetime import datetime

from pydantic import BaseModel


class AiHelperRunCreate(BaseModel):
    # 'read' (write to a target output column) | 'edit' (rewrite in place)
    mode: str = "read"
    prompt: str
    prompt_id: int | None = None  # provenance if loaded from the library
    name: str | None = None
    # {var_name: source_column_id} — the columns the prompt reads.
    variable_map: dict[str, int] = {}
    # read: output column; edit: column rewritten (must be a mapped input).
    target_column_id: int
    provider_code: str | None = None
    model: str | None = None
    max_output_tokens: int | None = None
    # 'full' | 'first_pct' (word-slice the sliced column's first input_pct%).
    input_scope: str = "full"
    input_pct: int | None = None
    slice_column_id: int | None = None
    # Explicit rows to process (selection / range / filter, resolved by the UI);
    # empty = every row in the table.
    row_ids: list[int] = []


class AiHelperCellRead(BaseModel):
    id: int
    row_id: int
    row_position: int
    column_id: int
    state: str  # pending | done | failed | skipped
    old_value: str | None = None
    new_value: str | None = None
    error: str | None = None


class AiHelperRunRead(BaseModel):
    id: int
    table_id: int
    status: str  # queued | running | cancelled | done | failed
    mode: str
    name: str | None = None
    target_column_id: int | None = None
    total: int
    done: int
    failed: int
    skipped: int
    reverted_at: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AiHelperRunDetail(AiHelperRunRead):
    prompt: str = ""
    variable_map: dict = {}
    provider_code: str | None = None
    model: str | None = None
    input_scope: str = "full"
    input_pct: int | None = None
    error: str | None = None
    items: list[AiHelperCellRead] = []
    items_total: int = 0
    items_page: int = 1
    items_page_size: int = 50


class AiHelperPreview(BaseModel):
    """Pre-run estimate for the cost gate."""

    matched_rows: int
    provider_code: str | None = None
    model: str | None = None
    # Best-effort upper-bound cost; null when the model has no configured rate.
    est_cost_usd: float | None = None
    est_input_tokens_avg: int | None = None
    provider_configured: bool = False
