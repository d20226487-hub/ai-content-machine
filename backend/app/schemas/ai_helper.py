"""Schemas for the AI Helper bulk-table mini-tool (v1.1: multi-output)."""
from datetime import datetime

from pydantic import BaseModel


class AiHelperOutput(BaseModel):
    """One output column a run writes/edits."""

    column_id: int
    # 'write' (produce new content for the column) | 'edit' (rewrite in place;
    # the column must also be a mapped input so the model sees its content).
    mode: str = "write"
    # JSON key the structured engine routes to this column (auto-slugged from the
    # column name in the UI, editable). Unused by the per_output engine.
    key: str = ""
    # This output's own prompt (per_output engine only; may contain {{vars}}).
    prompt: str = ""


class AiHelperRunCreate(BaseModel):
    # 'structured' (1 AI call/row → JSON keyed by output) | 'per_output'
    # (1 AI call per output, each with its own prompt).
    engine: str = "structured"
    # Structured: the shared base prompt. per_output: optional (each output
    # carries its own prompt); kept for the run summary.
    prompt: str = ""
    prompt_id: int | None = None  # provenance if loaded from the library
    name: str | None = None
    # {var_name: source_column_id} — the columns the prompt(s) read.
    variable_map: dict[str, int] = {}
    # The columns this run writes/edits (≥1; column ids unique).
    outputs: list[AiHelperOutput] = []
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
    mode: str  # legacy single-output mode (v1.1 runs: informational)
    engine: str  # structured | per_output
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
    # Effective outputs (synthesized from target_column_id/mode for legacy runs).
    outputs: list[AiHelperOutput] = []
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
    # Total AI calls: matched_rows (structured) or matched_rows × #outputs.
    est_calls: int = 0
    provider_code: str | None = None
    model: str | None = None
    # Best-effort upper-bound cost; null when the model has no configured rate.
    est_cost_usd: float | None = None
    est_input_tokens_avg: int | None = None
    provider_configured: bool = False
