from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ColumnKind = Literal["input", "output"]
CellStatus = Literal["empty", "manual", "generating", "generated", "failed"]


# ----- Columns -----

class ColumnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    name: str
    kind: ColumnKind
    prompt_id: int | None
    prompt_version_number: int | None
    variable_map: dict[str, int]
    provider_code: str | None
    model: str | None


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ColumnKind = "input"
    position: int | None = None  # appended at the end if omitted
    prompt_id: int | None = None
    prompt_version_number: int | None = None
    variable_map: dict[str, int] = Field(default_factory=dict)
    provider_code: str | None = None
    model: str | None = None


class ColumnUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: ColumnKind | None = None
    position: int | None = None
    prompt_id: int | None = None
    prompt_version_number: int | None = None
    variable_map: dict[str, int] | None = None
    provider_code: str | None = None
    model: str | None = None


# ----- Rows -----

class RowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int


# ----- Cells -----

class CellTranslation(BaseModel):
    """One memoized translation entry for a single cell."""

    text: str
    provider_used: str | None = None
    model_used: str | None = None
    translated_at: datetime | None = None


class CellRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_id: int
    column_id: int
    value: str | None
    status: CellStatus
    error: str | None
    model_used: str | None
    generated_at: datetime | None
    updated_at: datetime
    # Lowercase language tag → CellTranslation. Absent when no
    # translation has ever been requested for this cell.
    translations: dict[str, CellTranslation] | None = None


class CellUpsert(BaseModel):
    """A single cell write keyed by (row_id, column_id). value=null clears it."""

    row_id: int
    column_id: int
    value: str | None = None
    # If omitted, value-only writes default to 'manual' (or 'empty' when value is null).
    status: CellStatus | None = None


class CellsBatchUpsert(BaseModel):
    cells: list[CellUpsert]


# ----- Tables -----

class TableListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    folder_id: int | None = None
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    column_count: int = 0
    row_count: int = 0
    # Populated by the trash list endpoint only; null on the normal list.
    deleted_at: datetime | None = None


class TableListResponse(BaseModel):
    """Paginated wrapper for the bulk-tables list."""

    items: list[TableListItem]
    total: int
    page: int
    page_size: int


class TableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    folder_id: int | None = None
    created_by_id: int | None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    columns: list[ColumnRead] = []
    rows: list[RowRead] = []
    cells: list[CellRead] = []


class TrashBulkIds(BaseModel):
    """Body for POST /library/trash/bulk-restore and DELETE /library/trash/bulk."""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


# ----- Folders (bulk-table organization) -----

class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    # Populated when ?with_counts=true
    table_count: int | None = None


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    folder_id: int | None = None
    # If provided, table is initialized with these column names (all 'input').
    initial_columns: list[str] = Field(default_factory=list)
    # Optional: number of empty rows to create up front. Default = 5.
    initial_row_count: int = Field(default=5, ge=0, le=10_000)


class TableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    # null clears the folder; omit the field to leave folder unchanged.
    folder_id: int | None = None


class TableBulkMove(BaseModel):
    """Body for ``POST /library/tables/bulk-move``.

    Mirrors ``DomainBulkMove`` so the frontend's MoveToFolderModal can
    use the same shape across surfaces. ``folder_id`` is required here
    (not Optional in the sense of "omit to leave unchanged"); pass
    ``null`` to move out of any folder.
    """

    table_ids: list[int] = Field(min_length=1, max_length=10_000)
    folder_id: int | None


# ----- CSV import -----

class CsvImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    csv_text: str = Field(min_length=1)
    # Common defaults; can be overridden by the client.
    delimiter: str = ","
    has_header: bool = True


# ----- Generation -----

class GenerateRequest(BaseModel):
    """Enqueue generation for a set of (row, column) cells.

    If `row_ids` is omitted, ALL rows are targeted.
    If `column_ids` is omitted, every output column with a prompt is targeted.

    `mode` decides which cells in the row×column matrix are eligible:
      * 'empty'  — cells with no existing 'generated' value (default)
      * 'failed' — only cells whose status is 'failed'
      * 'all'    — every cell, overwriting whatever was there

    The legacy `overwrite=True` flag is still accepted; it now means mode='all'.
    """

    row_ids: list[int] | None = None
    column_ids: list[int] | None = None
    mode: Literal["empty", "failed", "all"] = "empty"
    # Deprecated alias kept for back-compat. Prefer `mode`.
    overwrite: bool = False

    # Queue-wide override: when set, every cell in this run uses these
    # values instead of the per-column provider_code / model. Useful for
    # one-off A/B tests, retrying with a more reliable provider, or running
    # a cheap model across an expensive table without re-configuring N
    # columns. Both must be set together; setting only one is a 400.
    override_provider_code: str | None = None
    override_model: str | None = None


class GenerateResponse(BaseModel):
    enqueued_cell_ids: list[int]
    skipped: int
    message: str
    # New in migration 0030: when at least one cell is enqueued, a
    # BulkGenerationRun is created and its id surfaces here so the
    # editor UI can immediately link to the progress banner / detail
    # page. None when nothing was enqueued (no cells matched the
    # filter, no rows, etc.) — no run, no id.
    run_id: int | None = None


# ----- Generation runs (added in migration 0030) -----

BulkGenerationRunStatus = Literal[
    "queued", "running", "cancelled", "done", "failed"
]


class BulkGenerationRunRead(BaseModel):
    """One bulk-generation run — counters + lifecycle stamps. Used by
    both the polled detail page and the inline editor banner."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    status: BulkGenerationRunStatus
    total: int
    done: int
    failed: int
    skipped: int
    error: str | None = None
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class BulkGenerationRunDetail(BulkGenerationRunRead):
    """Same payload as the summary today — kept as a separate type so
    we can extend with per-error breakdowns / per-column counts later
    without breaking the summary endpoint."""

    created_by_name: str | None = None
