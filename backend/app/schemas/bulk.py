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
    # Autotool (3rd publishing mode): whether this table is exposed as a
    # public CSV and the token that forms its URL (null when disabled).
    autotool_enabled: bool = False
    autotool_token: str | None = None
    # Per-site planned page list for Google-Docs-imported tables (drives the
    # "Site structure" reference panel). None for tables not built that way.
    gdocs_structure: list[dict] | None = None
    # Per-row AI slug mapping (anchor → final slug) for review. None otherwise.
    gdocs_slug_audit: list[dict] | None = None
    columns: list[ColumnRead] = []
    rows: list[RowRead] = []
    cells: list[CellRead] = []
    # Total rows in the table regardless of pagination. When the fetch is
    # paginated, `rows`/`cells` hold only the requested page while this
    # reflects the whole table (footer + selection math). On a full
    # (unpaginated) fetch it equals len(rows).
    total_row_count: int = 0


class AutotoolState(BaseModel):
    """Lightweight result of toggling a table's Autotool exposure.

    Returned by the enable/disable endpoints instead of the full TableRead so
    a large table doesn't ship every cell on a one-click toggle. ``csv_path``
    is the relative public path the frontend resolves against the API origin.
    """

    autotool_enabled: bool
    autotool_token: str | None = None
    csv_path: str | None = None


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


class DiffBlock(BaseModel):
    """One aligned block of a Before/After diff, shared by both sides so the two
    panes snippet in step. ``before``/``after`` are the per-side text (either may
    be empty for a pure insert/delete); ``changed`` marks a replaced span."""

    before: str
    after: str
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


class TranslationCheckConfig(BaseModel):
    """Config for the translation-links mode (3rd mode).

    Three column roles: ``original`` (source-language content whose links are
    localized), ``translated`` (the translation whose links are checked), and
    ``lang`` (the target language code per row, used verbatim as the subfolder).

    Link type is decided by domain: ``internal_domain_column_ids`` name the
    column(s) that hold each row's own site domain (links on those hosts are
    internal); ``product_domain`` (one or a few, comma/space separated) marks
    product links. Only ``exceptions`` is a bulk textarea ("language, page" per
    line; those pages keep their root URL). Treatments: products always
    localize (minus exceptions); internal & external are skip-or-localize."""

    original_column_id: int
    translated_column_id: int
    lang_column_id: int
    # Columns whose values are this row's internal site domain(s).
    internal_domain_column_ids: list[int] = Field(default_factory=list)
    # Product domain(s) — links on these hosts are products.
    product_domain: str = ""
    # One "language, page" per line; the page keeps its root URL (no subfolder).
    exceptions: str = ""
    # One "domain, lang" per line: the language that domain serves at its ROOT
    # (no subfolder). When a product link's target language is the site default,
    # the expected link stays at the root instead of getting a /<lang>/ prefix.
    product_default_langs: str = ""
    internal_treatment: Literal["skip", "localize"] = "skip"
    external_treatment: Literal["skip", "localize"] = "skip"

    @model_validator(mode="after")
    def _distinct(self) -> "TranslationCheckConfig":
        ids = {
            self.original_column_id,
            self.translated_column_id,
            self.lang_column_id,
        }
        if len(ids) < 3:
            raise ValueError(
                "Original, Translated, and Lang must be three different columns."
            )
        return self


class LinkCheckRequest(BaseModel):
    """Start a link-check run.

    ``column_ids`` are the output columns to scan (at least one).
    ``check_juxtapose`` compares against the union of ``expected_column_ids``
    (at least one required when juxtapose is on). ``check_crawl`` fetches each
    link to verify its HTTP status; ``include_ok`` additionally records the
    healthy links. At least one check must be enabled.

    ``translation`` selects the 3rd mode instead — when set, the other checks
    are ignored (the server runs a computed-expected juxtapose)."""

    column_ids: list[int] = Field(default_factory=list)
    expected_column_ids: list[int] = Field(default_factory=list)
    check_juxtapose: bool = False
    check_crawl: bool = False
    include_ok: bool = False
    # Optional link-type classification (product / internal / external) for the
    # crawl/juxtapose findings — mirrors translation mode. ``product_domain`` is
    # comma/space/newline-separated; internal domains come per-row from the
    # chosen column(s). When neither is set, no link-type filter is offered.
    product_domain: str = ""
    internal_domain_column_ids: list[int] = Field(default_factory=list)
    translation: TranslationCheckConfig | None = None

    @model_validator(mode="after")
    def _validate(self) -> "LinkCheckRequest":
        if self.translation is not None:
            return self  # translation mode has its own column roles
        if not self.column_ids:
            raise ValueError("Select at least one column to scan.")
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
    # Present (non-NULL) only for translation-mode runs; the frontend uses it
    # to label the run and surface the computed-expected-links column.
    translation_config: dict | None = None
    # Present (non-NULL) when the crawl/juxtapose run classified links by type;
    # the frontend shows the product/internal/external filter when it's set.
    classify_config: dict | None = None


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
    # product | internal | external (None when the run didn't classify).
    link_type: Literal["product", "internal", "external"] | None = None
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
    # Crawl status-class breakdown (unique-URL based, from crawl targets) for
    # the status-code overview. 404 = "битые"; 5xx/3xx/2xx are whole classes.
    status_2xx: int = 0
    status_3xx: int = 0
    status_404: int = 0
    status_5xx: int = 0
    items: list[LinkViolationRead]


class TranslationLinkTag(BaseModel):
    """A translation link tagged by how it compares to the expected links:
    ok (matches), discrepancy (wrong but relates to an original link), or
    invented (made-up, no basis in the original). ``dismissed`` = the user
    bulk-dismissed this error from the active view.

    ``expected`` is the link this one SHOULD have been (only set for a
    discrepancy that pairs to an expected link); the raw table uses it to
    underline just the drifting part when the host matches. ``link_type``
    labels the link in the folded translation column."""

    url: str
    kind: Literal["ok", "discrepancy", "invented"]
    dismissed: bool = False
    # A wrong link that a fix/replace run has since corrected — the overview
    # shows it struck through so reviewers can see what was already handled.
    resolved: bool = False
    expected: str | None = None
    # The original (source) link this discrepancy was paired to, so the raw
    # table can show it aligned beside the wrong translation link. None for an
    # invented link or a "no good match" leftover.
    original: str | None = None
    link_type: Literal["product", "internal", "external"] | None = None


class DismissItem(BaseModel):
    row_id: int
    link: str


class DismissRequest(BaseModel):
    """Bulk dismiss/restore of translation-table errors (per row+link)."""

    items: list[DismissItem] = Field(default_factory=list)


class AlignedRow(BaseModel):
    """An expected link paired with the WRONG translation link it should have
    been (``wrong`` None = correct/omitted). For invented links ``expected`` is
    None. ``link_type`` (product/internal/external, or invented) drives the
    link-type filter. Drives the side-by-side expected↔discrepancy alignment."""

    expected: str | None = None
    wrong: TranslationLinkTag | None = None
    link_type: Literal["product", "internal", "external"] = "external"


class TranslationTableRow(BaseModel):
    """One row of the translation raw-table view: the link breakdown, computed
    on demand (not stored). ``translation`` links are tagged; ``aligned`` pairs
    each expected link with its wrong counterpart; ``has_discrepancy`` drives
    the discrepancy filter."""

    row_id: int
    row_position: int
    lang: str = ""
    original: list[str]
    translation: list[TranslationLinkTag]
    aligned: list[AlignedRow]
    has_discrepancy: bool


class TranslationTableResponse(BaseModel):
    page: int
    page_size: int
    total_rows: int
    items: list[TranslationTableRow]


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
    # Translation-overview link-type filter. When set, only that type's
    # violations are fixed, mirroring what the table is showing (product /
    # internal / external). Translation runs don't persist link_type on the
    # violation rows, so the endpoint classifies each link's host to match.
    link_type: Literal["product", "internal", "external"] | None = None
    # Where corrected content goes. Provide an existing column id, OR a
    # new_column_name to create one (keeps the original output intact). Both
    # omitted = overwrite the scanned source column.
    target_column_id: int | None = None
    new_column_name: str | None = Field(default=None, max_length=120)
    # Per-job correction prompt (system prompt override). None/empty = use the
    # global Brain ``fix_links`` prompt.
    prompt: str | None = None


class LinkFixDefaultPrompt(BaseModel):
    """Default correction prompt for the fix modal — the previously-used job
    prompt for this table, else the Brain ``fix_links`` default."""

    prompt: str


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
    prompt: str | None = None
    # 'ai' (LLM rewrite) | 'replace' (deterministic link swap). Drives the
    # run's display name so the two job kinds read distinctly in the history.
    method: Literal["ai", "replace"] = "ai"
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
    # Last per-cell progress stamp — drives the run page's "stalled?" check so
    # Resume is only offered when a running job has actually gone quiet.
    last_progress_at: datetime | None = None


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
    # Aligned char-level diff of source_value → new_value: one shared block list
    # so the Before/After panes collapse the same regions and stay lined up.
    diff_blocks: list[DiffBlock] = []


class LinkFixRunDetail(LinkFixRunRead):
    created_by_name: str | None = None
    page: int
    page_size: int
    total_cells: int
    items: list[LinkFixCellRead]


class LinkFixRevertResult(LinkFixRunRead):
    """Outcome of reverting a fix run: the run plus how many done cells were
    actually restored vs. skipped because they no longer hold what the fix
    wrote (a later edit or a newer fix run changed them). Lets the UI explain a
    partial / no-op revert instead of looking like nothing happened."""

    reverted_count: int
    skipped_count: int


class TableFixedCell(BaseModel):
    """A cell corrected by an applied (non-reverted) fix run — drives the
    grid's green tint and the cell editor's "Changes" diff view."""

    row_id: int
    column_id: int
    segments: list[UnifiedSegment]


# ----- Google-Docs importer (added in migration 0048) -----

GdocsImportStatus = Literal["queued", "running", "cancelled", "done", "failed"]


class GdocsImportRunRead(BaseModel):
    """Summary of a Google-Docs import run — drives the history list + the
    progress page polling. ``payload`` is intentionally NOT exposed (it carries
    the full Doc HTML and can be multi-MB)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: GdocsImportStatus
    table_name: str
    target_folder_id: int | None = None
    mode: str | None = None
    # Per-import AI override (NULL = first-enabled provider + its default model).
    provider_code: str | None = None
    model: str | None = None
    result_table_id: int | None = None
    total_docs: int
    docs_done: int
    docs_failed: int
    total_pages: int
    pages_matched: int
    pages_unmatched: int
    # Planned Structure entries across all sites (coverage denominator).
    total_structure_pages: int = 0
    rows_built: int
    warnings: list[str] = []
    error: str | None = None
    created_by_id: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_progress_at: datetime | None = None
