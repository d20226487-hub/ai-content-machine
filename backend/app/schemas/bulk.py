from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    # Total rows in the table regardless of pagination. When the fetch is
    # paginated, `rows`/`cells` hold only the requested page while this
    # reflects the whole table (footer + selection math). On a full
    # (unpaginated) fetch it equals len(rows).
    total_row_count: int = 0


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

class RunRename(BaseModel):
    """Body for renaming any tool run. Empty/blank clears the custom name
    (UI falls back to the "<tool> #<id>" label)."""

    name: str | None = Field(default=None, max_length=200)


class RowRange(BaseModel):
    """A 1-based, inclusive ordinal row range (the visible '#' numbers in the
    grid, i.e. ordinal positions in the position-ordered row list — NOT the
    raw `position` values, which may be sparse)."""

    start: int = Field(ge=1)
    end: int = Field(ge=1)


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
    # 1-based ordinal range (alternative to row_ids). When set, targets the
    # rows at those ordinal positions in the position-ordered list. Ignored
    # when row_ids is provided.
    row_range: RowRange | None = None
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


class GeneratePreviewResponse(BaseModel):
    """Dry-run of a GenerateRequest: how many cells WOULD be enqueued vs
    skipped, using the exact same resolver as the enqueue endpoint."""

    will_generate: int
    skipped: int


class ClearValuesRequest(BaseModel):
    """Server-side bulk clear of cell values. Either pass explicit
    ``row_ids`` (clears those rows) or ``all=True`` (clears every row in the
    table). ``all`` wins if both are set. Used by the grid's 'Clear values'
    when the selection spans pages (select-all-N)."""

    row_ids: list[int] | None = None
    all: bool = False


class ClearValuesResponse(BaseModel):
    cleared: int


class ColumnValueRow(BaseModel):
    id: int
    position: int


class ColumnValuesResponse(BaseModel):
    """Lightweight per-column values for the publish modal previews. Returns
    the full ordered row list (ids + ordinal positions) plus the values of
    ONLY the requested columns — never the heavy output cells."""

    rows: list[ColumnValueRow]
    # row_id -> { column_id -> value }
    values: dict[int, dict[int, str]]


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
    name: str | None = None
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


# ----- Find / replace (added in migration 0033) -----


class FindReplaceConfig(BaseModel):
    """Shared search configuration for both Find and Replace.

    ``column_ids`` empty = search every column. ``replacement`` is ignored
    by the Find endpoint.
    """

    pattern: str = Field(min_length=1)
    replacement: str = ""
    is_regex: bool = False
    case_sensitive: bool = True
    whole_cell: bool = False
    column_ids: list[int] = Field(default_factory=list)


class FindRequest(FindReplaceConfig):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=500)


class ReplaceRequest(FindReplaceConfig):
    pass


class MatchedCell(BaseModel):
    """One cell that matched, with enough context to render a results row
    and open it in the editor."""

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    value: str
    status: CellStatus
    match_count: int


class FindResponse(BaseModel):
    total_matches: int  # total occurrences across all matched cells
    total_cells: int  # distinct cells with at least one match
    page: int
    page_size: int
    items: list[MatchedCell]


class FindReplaceRunRead(BaseModel):
    """Summary of a replace run — drives the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    name: str | None = None
    pattern: str
    replacement: str
    is_regex: bool
    case_sensitive: bool
    whole_cell: bool
    column_ids: list[int]
    match_count: int
    cell_count: int
    status: Literal["applied", "reverted"]
    created_by_id: int | None
    created_at: datetime
    reverted_at: datetime | None = None


class HighlightSegment(BaseModel):
    """One run of text in a before/after diff. ``changed`` marks the matched
    span (old side) or the inserted replacement (new side)."""

    text: str
    changed: bool


class DiffSegment(BaseModel):
    """One span of a two-sided diff. ``changed`` spans are struck red on the
    Before side / highlighted green on the After side."""

    text: str
    changed: bool


class UnifiedSegment(BaseModel):
    """One span of a single-pane diff: ``add`` green, ``del`` red+struck,
    ``equal`` plain."""

    text: str
    kind: Literal["equal", "add", "del"]


class ReplacedCell(BaseModel):
    """One affected cell on the run detail page. ``current_value`` is the
    cell's value right now; ``drifted`` is True when it no longer equals the
    value the replace wrote (someone edited or regenerated it since), so the
    UI can warn that reverting would discard that later change.

    ``old_segments`` / ``new_segments`` split the before/after text so the UI
    can strike only the matched part and highlight only the inserted part."""

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    old_value: str | None
    new_value: str | None
    current_value: str | None
    current_status: CellStatus
    drifted: bool
    old_segments: list[HighlightSegment]
    new_segments: list[HighlightSegment]


class FindReplaceRunDetail(FindReplaceRunRead):
    created_by_name: str | None = None
    page: int
    page_size: int
    total_cells: int  # == cell_count, echoed for pagination math
    drifted_count: int
    items: list[ReplacedCell]


# ----- Structure & Formatting (added in migration 0040) -----

# The selectable transforms. Applied in THIS canonical order regardless of the
# order they arrive in (mirrors services/structure_format.OPERATIONS).
StructureFormatOp = Literal[
    "markdown", "response_start", "inline_css", "html_format"
]


StructureFormatStatus = Literal[
    "queued", "running", "done", "failed", "cancelled"
]


class StructureFormatRequest(BaseModel):
    """Run a subset of the structure/formatting transforms across the chosen
    columns. ``column_ids`` empty = every column. At least one operation is
    required (validated in the endpoint)."""

    operations: list[StructureFormatOp] = Field(default_factory=list)
    column_ids: list[int] = Field(default_factory=list)


class StructureFormatPreviewCell(BaseModel):
    """One cell that would change, for the preview's scope table — same
    Applied / Changes shape as the result table, without writing anything."""

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    applied_ops: list[str] = []
    change_segments: list[UnifiedSegment] = []


class StructureFormatPreview(BaseModel):
    """Dry-run impact: counts + a paginated sample of the cells that would
    change (with the Applied/Changes view), so the user sees the scope before
    applying."""

    candidates: int  # non-empty cells in scope
    would_change: int  # of those, how many the transforms would alter
    page: int
    page_size: int
    items: list[StructureFormatPreviewCell] = []


class StructureFormatRunRead(BaseModel):
    """Summary of a structure-format run — drives the history list + polling."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    name: str | None = None
    operations: list[str]
    column_ids: list[int]
    status: StructureFormatStatus
    total: int
    done: int
    failed: int
    cell_count: int
    reverted_at: datetime | None = None
    error: str | None = None
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StructureFormatCell(BaseModel):
    """One affected cell on the run detail page. ``drifted`` is True when the
    cell was edited since the run (reverting would discard that change).

    ``change_segments`` is a CONDENSED single-pane diff (old→new) — long
    unchanged stretches are elided so the changes stay visible in a huge HTML
    cell. ``applied_ops`` is the subset of the run's transforms that actually
    changed THIS cell."""

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    old_value: str | None
    new_value: str | None
    current_value: str | None
    current_status: CellStatus
    drifted: bool
    applied_ops: list[str] = []
    change_segments: list[UnifiedSegment] = []


class StructureFormatRunDetail(StructureFormatRunRead):
    created_by_name: str | None = None
    page: int
    page_size: int
    total_cells: int  # == cell_count, echoed for pagination math
    drifted_count: int
    items: list[StructureFormatCell]


# ----- Link checker (added in migration 0034) -----

LinkCheckStatus = Literal["queued", "running", "cancelled", "done", "failed"]
LinkProblem = Literal["omitted", "hallucinated", "broken", "ok"]


class LinkCheckRequest(BaseModel):
    """Start a link-check run.

    ``column_ids`` are the output columns to scan (at least one).
    ``check_juxtapose`` compares against the union of ``expected_column_ids``
    (at least one required when juxtapose is on). ``check_crawl`` fetches each
    link to verify its HTTP status; ``include_ok`` additionally records the
    healthy links. At least one check must be enabled."""

    column_ids: list[int] = Field(min_length=1)
    expected_column_ids: list[int] = Field(default_factory=list)
    check_juxtapose: bool = False
    check_crawl: bool = False
    include_ok: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "LinkCheckRequest":
        if not self.check_juxtapose and not self.check_crawl:
            raise ValueError("Enable at least one check (juxtapose or crawl).")
        if self.check_juxtapose and not self.expected_column_ids:
            raise ValueError(
                "At least one expected-links column is required for juxtapose."
            )
        return self


class LinkCheckRunRead(BaseModel):
    """Run summary — counters + lifecycle. Polled by the run page while the
    crawl is in flight, and used for the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    name: str | None = None
    status: LinkCheckStatus
    column_ids: list[int]
    expected_column_ids: list[int]
    check_juxtapose: bool
    check_crawl: bool
    include_ok: bool
    total_links: int
    crawled: int
    ok_count: int
    broken_count: int
    omitted_count: int
    hallucinated_count: int
    error: str | None = None
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# Resolution stamp from the in-place AI re-verify (None = untouched).
LinkResolution = Literal["solved", "unsolved"]


class LinkViolationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    problem: LinkProblem
    link: str
    detail_code: str | None = None
    status_code: int | None = None
    # None = untouched; set by the in-place re-verify after an AI fix.
    resolution: LinkResolution | None = None


class LinkCheckRunDetail(LinkCheckRunRead):
    created_by_name: str | None = None
    page: int
    page_size: int
    total_violations: int  # count AFTER filters, for pagination
    # Distinct HTTP codes present across the run's violations (unfiltered) —
    # populates the status-code filter dropdown.
    status_codes_present: list[int]
    items: list[LinkViolationRead]


# ----- AI link fix (added in migration 0037) -----

LinkFixStatus = Literal["queued", "running", "cancelled", "done", "failed"]


class LinkFixRequest(BaseModel):
    """Start an AI link-fix run off a completed check run.

    ``row_ids`` empty/None = fix every flagged row; otherwise only those
    rows. Only omitted / broken / hallucinated violations are fixable.

    The optional filters mirror the run page's filter bar so "Fix all" sends
    only what's currently shown (e.g. just the hallucinated links), not every
    violation. Per cell, only the matching violations are handed to the AI."""

    source_run_id: int
    row_ids: list[int] | None = None
    # Same filters as GET /link-check-runs/{id}.
    problem: LinkProblem | None = None
    status_code: int | None = None
    q: str | None = None
    # When true, ``q`` is a "does NOT contain" filter.
    q_negate: bool = False
    # Where corrected content goes. Provide an existing column id, OR a
    # new_column_name to create one (keeps the original output intact). Both
    # omitted = overwrite the scanned source column.
    target_column_id: int | None = None
    new_column_name: str | None = Field(default=None, max_length=120)


class LinkFixRunRead(BaseModel):
    """Run summary — counters + lifecycle. Polled by the fix-run page while
    active, and used for the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: int
    name: str | None = None
    source_run_id: int | None
    recheck_run_id: int | None
    target_column_id: int | None = None
    status: LinkFixStatus
    column_ids: list[int]
    expected_column_ids: list[int]
    total: int
    done: int
    failed: int
    skipped: int
    reverted_at: datetime | None = None
    error: str | None = None
    created_by_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class LinkFixViolationLite(BaseModel):
    problem: LinkProblem
    link: str
    detail_code: str | None = None
    status_code: int | None = None


class LinkFixCellRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_id: int
    row_position: int
    column_id: int
    column_name: str
    state: Literal["pending", "done", "failed", "skipped"]
    # Original source content (before); the corrected result (after).
    source_value: str | None = None
    old_value: str | None
    new_value: str | None
    violations: list[LinkFixViolationLite]
    error: str | None = None
    # Char-level diff of source_value → new_value (Before / After highlight).
    before_segments: list[DiffSegment] = []
    after_segments: list[DiffSegment] = []


class LinkFixRunDetail(LinkFixRunRead):
    created_by_name: str | None = None
    page: int
    page_size: int
    total_cells: int
    items: list[LinkFixCellRead]


class TableFixedCell(BaseModel):
    """A cell corrected by an applied (non-reverted) fix run — drives the
    grid's green tint and the cell editor's "Changes" diff view."""

    row_id: int
    column_id: int
    segments: list[UnifiedSegment]
