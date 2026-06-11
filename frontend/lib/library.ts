import { api, getToken } from "./api";
import type {
  BulkColumn,
  BulkRow,
  BulkTable,
  BulkTableListItem,
  ColumnKind,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ----- Tables -----

export interface CreateTablePayload {
  name: string;
  description?: string | null;
  folder_id?: number | null;
  initial_columns?: string[];
  initial_row_count?: number;
}

export interface TableListResponse {
  items: BulkTableListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ListTablesOpts {
  /** null = all, 0 = uncategorized, N = inside folder N */
  folder_id?: number | null;
  q?: string;
  page?: number;
  page_size?: number;
}

export function listTables(opts: ListTablesOpts = {}): Promise<TableListResponse> {
  const sp = new URLSearchParams();
  if (opts.folder_id != null) sp.set("folder_id", String(opts.folder_id));
  if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
  if (opts.page) sp.set("page", String(opts.page));
  if (opts.page_size) sp.set("page_size", String(opts.page_size));
  const qs = sp.toString();
  return api<TableListResponse>(`/library/tables${qs ? "?" + qs : ""}`);
}

export interface GetTableOpts {
  /** 1-based page index. Omit (with page_size) for the full table. */
  page?: number;
  page_size?: number;
}

export function getTable(id: number, opts: GetTableOpts = {}): Promise<BulkTable> {
  const sp = new URLSearchParams();
  if (opts.page != null && opts.page_size != null) {
    sp.set("page", String(opts.page));
    sp.set("page_size", String(opts.page_size));
  }
  const qs = sp.toString();
  return api<BulkTable>(`/library/tables/${id}${qs ? "?" + qs : ""}`);
}

export function createTable(p: CreateTablePayload): Promise<BulkTable> {
  return api<BulkTable>("/library/tables", { method: "POST", body: p });
}

export function renameTable(
  id: number,
  patch: { name?: string; description?: string | null; folder_id?: number | null },
): Promise<BulkTableListItem> {
  return api<BulkTableListItem>(`/library/tables/${id}`, {
    method: "PATCH",
    body: patch,
  });
}

/**
 * Move N tables to a folder (or out of any folder) in one round-trip.
 *
 * `folder_id` semantics here are NOT the same as `listTables`:
 *   * `null` = move out of any folder (uncategorized)
 *   * any positive integer = the target folder id
 * (There's no "leave folder unchanged" option — that's what `renameTable`
 * with a body that omits `folder_id` is for.)
 */
export function bulkMoveTables(payload: {
  table_ids: number[];
  folder_id: number | null;
}): Promise<{ moved: number }> {
  return api<{ moved: number }>("/library/tables/bulk-move", {
    method: "POST",
    body: payload,
  });
}

// ----- Folders -----

export interface BulkFolder {
  id: number;
  name: string;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  table_count?: number | null;
}

export function listFolders(opts: { with_counts?: boolean } = {}): Promise<BulkFolder[]> {
  const qs = opts.with_counts ? "?with_counts=true" : "";
  return api<BulkFolder[]>(`/library/folders${qs}`);
}

export function createFolder(name: string): Promise<BulkFolder> {
  return api<BulkFolder>("/library/folders", { method: "POST", body: { name } });
}

export function renameFolder(id: number, name: string): Promise<BulkFolder> {
  return api<BulkFolder>(`/library/folders/${id}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteFolder(id: number): Promise<void> {
  return api<void>(`/library/folders/${id}`, { method: "DELETE" });
}

/** Soft-delete (move to trash). Refuses with 409 if a bulk publish run
 *  is in flight against this table. */
export function deleteTable(id: number): Promise<void> {
  return api<void>(`/library/tables/${id}`, { method: "DELETE" });
}

export function duplicateTable(id: number): Promise<BulkTable> {
  return api<BulkTable>(`/library/tables/${id}/duplicate`, { method: "POST" });
}

// ----- Trash -----

export function listTrash(opts: { q?: string; page?: number; page_size?: number } = {}): Promise<TableListResponse> {
  const sp = new URLSearchParams();
  if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
  if (opts.page) sp.set("page", String(opts.page));
  if (opts.page_size) sp.set("page_size", String(opts.page_size));
  const qs = sp.toString();
  return api<TableListResponse>(`/library/trash${qs ? "?" + qs : ""}`);
}

export function getTrashCount(): Promise<{ count: number }> {
  return api<{ count: number }>("/library/trash/count");
}

export function previewTrashedTable(id: number): Promise<BulkTable> {
  return api<BulkTable>(`/library/trash/${id}`);
}

export function restoreTable(id: number): Promise<BulkTableListItem> {
  return api<BulkTableListItem>(`/library/tables/${id}/restore`, { method: "POST" });
}

export function permanentlyDeleteTable(id: number): Promise<void> {
  return api<void>(`/library/tables/${id}/permanent`, { method: "DELETE" });
}

export function emptyTrash(): Promise<{ deleted: number }> {
  return api<{ deleted: number }>("/library/trash", { method: "DELETE" });
}

export function bulkRestoreTrash(ids: number[]): Promise<{ restored: number }> {
  return api<{ restored: number }>("/library/trash/bulk-restore", {
    method: "POST",
    body: { ids },
  });
}

export function bulkPermanentlyDelete(ids: number[]): Promise<{ deleted: number }> {
  return api<{ deleted: number }>("/library/trash/bulk", {
    method: "DELETE",
    body: { ids },
  });
}

export interface TrashRetention {
  days: number;
  default: number;
  max: number;
}

export function getTrashRetention(): Promise<TrashRetention> {
  return api<TrashRetention>("/library/trash/retention");
}

export function setTrashRetention(days: number): Promise<TrashRetention> {
  return api<TrashRetention>("/library/trash/retention", {
    method: "PUT",
    body: { days },
  });
}

// ----- Columns -----

export interface CreateColumnPayload {
  name: string;
  kind?: ColumnKind;
  position?: number | null;
  prompt_id?: number | null;
  prompt_version_number?: number | null;
  variable_map?: Record<string, number>;
}

export function addColumn(tableId: number, p: CreateColumnPayload): Promise<BulkColumn> {
  return api<BulkColumn>(`/library/tables/${tableId}/columns`, {
    method: "POST",
    body: p,
  });
}

export interface UpdateColumnPayload {
  name?: string;
  kind?: ColumnKind;
  position?: number;
  prompt_id?: number | null;
  prompt_version_number?: number | null;
  variable_map?: Record<string, number>;
  provider_code?: string | null;
  model?: string | null;
}

export function updateColumn(
  tableId: number,
  columnId: number,
  patch: UpdateColumnPayload,
): Promise<BulkColumn> {
  return api<BulkColumn>(`/library/tables/${tableId}/columns/${columnId}`, {
    method: "PATCH",
    body: patch,
  });
}

export function deleteColumn(tableId: number, columnId: number): Promise<void> {
  return api<void>(`/library/tables/${tableId}/columns/${columnId}`, {
    method: "DELETE",
  });
}

// ----- Rows -----

export function addRow(tableId: number): Promise<BulkRow> {
  return api<BulkRow>(`/library/tables/${tableId}/rows`, { method: "POST" });
}

export function deleteRow(tableId: number, rowId: number): Promise<void> {
  return api<void>(`/library/tables/${tableId}/rows/${rowId}`, { method: "DELETE" });
}

// ----- Cells -----

export interface CellWrite {
  row_id: number;
  column_id: number;
  value: string | null;
  status?: "empty" | "manual" | "generating" | "generated" | "failed";
}

export interface CellWriteResponse {
  id: number;
  row_id: number;
  column_id: number;
  value: string | null;
  status: string;
  updated_at: string;
}

export function upsertCells(
  tableId: number,
  cells: CellWrite[],
): Promise<CellWriteResponse[]> {
  return api<CellWriteResponse[]>(`/library/tables/${tableId}/cells`, {
    method: "PUT",
    body: { cells },
  });
}

// ----- Generation -----

export type GenerateMode = "empty" | "failed" | "all";

export interface RowRange {
  /** 1-based inclusive ordinal positions (the grid's visible "#" numbers). */
  start: number;
  end: number;
}

export interface GenerateRequestPayload {
  row_ids?: number[];
  /** Alternative to row_ids: target an ordinal range. Ignored if row_ids set. */
  row_range?: RowRange;
  column_ids?: number[];
  mode?: GenerateMode;
  /** @deprecated use `mode: 'all'` */
  overwrite?: boolean;
  /** Queue-wide override: when set, every cell in this run uses these values
   * instead of per-column settings. Both must be sent together (validated server-side). */
  override_provider_code?: string | null;
  override_model?: string | null;
}

export interface GenerateResponsePayload {
  enqueued_cell_ids: number[];
  skipped: number;
  message: string;
  /** New in migration 0030: id of the BulkGenerationRun created for
   *  this batch. Null when nothing was enqueued. */
  run_id: number | null;
}

export function enqueueGeneration(
  tableId: number,
  payload: GenerateRequestPayload = {},
): Promise<GenerateResponsePayload> {
  return api<GenerateResponsePayload>(`/library/tables/${tableId}/generate`, {
    method: "POST",
    body: payload,
  });
}

export interface GeneratePreviewResponse {
  will_generate: number;
  skipped: number;
}

/** Dry-run a generation request: how many cells WOULD be enqueued vs skipped.
 *  Uses the same server-side resolver as enqueueGeneration. */
export function generatePreview(
  tableId: number,
  payload: GenerateRequestPayload = {},
): Promise<GeneratePreviewResponse> {
  return api<GeneratePreviewResponse>(
    `/library/tables/${tableId}/generate-preview`,
    { method: "POST", body: payload },
  );
}

/** Server-side bulk clear of cell values. Pass {all:true} to clear every
 *  row, or {row_ids} for specific rows. */
export function clearValues(
  tableId: number,
  payload: { row_ids?: number[]; all?: boolean },
): Promise<{ cleared: number }> {
  return api<{ cleared: number }>(`/library/tables/${tableId}/clear-values`, {
    method: "POST",
    body: payload,
  });
}

export interface ColumnValuesResponse {
  rows: { id: number; position: number }[];
  /** row_id -> { column_id -> value }. Keys are strings over the wire. */
  values: Record<number, Record<number, string>>;
}

/** Lightweight per-column values for the publish-modal previews. Returns the
 *  ordered row list + values of ONLY the requested columns (never the heavy
 *  output cells). */
export function getColumnValues(
  tableId: number,
  columnIds: number[],
): Promise<ColumnValuesResponse> {
  const qs = columnIds.length ? `?column_ids=${columnIds.join(",")}` : "";
  return api<ColumnValuesResponse>(
    `/library/tables/${tableId}/column-values${qs}`,
  );
}

// ----- Bulk generation runs -----

export type BulkGenerationRunStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

export interface BulkGenerationRun {
  id: number;
  table_id: number;
  name: string | null;
  status: BulkGenerationRunStatus;
  total: number;
  done: number;
  failed: number;
  skipped: number;
  error: string | null;
  created_by_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface BulkGenerationRunDetail extends BulkGenerationRun {
  created_by_name: string | null;
}

/** Returns the table's currently-active (queued/running) generation
 *  run, or null when nothing is in flight. The editor banner polls
 *  this every few seconds. */
export function getActiveGenerationRun(
  tableId: number,
): Promise<BulkGenerationRun | null> {
  return api<BulkGenerationRun | null>(
    `/library/tables/${tableId}/active-gen-run`,
  );
}

export function getGenerationRun(
  runId: number,
): Promise<BulkGenerationRunDetail> {
  return api<BulkGenerationRunDetail>(`/library/gen-runs/${runId}`);
}

/** Sets status='cancelled' on the run. In-flight cells finish; the
 *  next pick-up by workers short-circuits with a "Cancelled" note. */
export function cancelGenerationRun(runId: number): Promise<BulkGenerationRun> {
  return api<BulkGenerationRun>(`/library/gen-runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function renameGenerationRun(
  runId: number,
  name: string | null,
): Promise<BulkGenerationRun> {
  return api<BulkGenerationRun>(`/library/gen-runs/${runId}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteGenerationRun(runId: number): Promise<void> {
  return api<void>(`/library/gen-runs/${runId}`, { method: "DELETE" });
}

// ----- CSV -----

export interface ImportCsvPayload {
  name: string;
  /** The CSV file itself — streamed as multipart, not read into a string. */
  file: File;
  delimiter?: string;
  has_header?: boolean;
}

export function importCsv(p: ImportCsvPayload): Promise<BulkTable> {
  const fd = new FormData();
  fd.append("file", p.file);
  fd.append("name", p.name);
  fd.append("delimiter", p.delimiter ?? ",");
  fd.append("has_header", String(p.has_header ?? true));
  return api<BulkTable>("/library/tables/import-csv", {
    method: "POST",
    body: fd,
  });
}

/** Build a download URL with the auth token forwarded. Used for CSV export. */
export function exportCsvUrl(tableId: number): string {
  // Browsers won't add Authorization automatically; we trigger this via fetch+blob.
  return `${API_URL}/library/tables/${tableId}/export.csv`;
}

// ----- Update an existing table from CSV / pasted rows -----

export interface TableUpdateMapping {
  /** 0-based column position in the incoming (header-stripped) data. */
  source_index: number;
  column_id: number;
}

export interface TableUpdateRequest {
  rows: (string | null)[][];
  mappings: TableUpdateMapping[];
  match_mode: "key" | "order";
  source_key_index?: number | null;
  key_column_id?: number | null;
  case_insensitive_key?: boolean;
  skip_empty?: boolean;
}

export interface TableUpdateResult {
  matched_rows: number;
  unmatched_rows: number;
  updated_cells: number;
  affected_table_rows: number;
}

export function updateTableCells(
  tableId: number,
  req: TableUpdateRequest,
): Promise<TableUpdateResult> {
  return api<TableUpdateResult>(`/library/tables/${tableId}/update-cells`, {
    method: "POST",
    body: req,
  });
}

export interface UpdateTableCsvParams {
  /** Streamed as multipart — the server parses it (same 100 MB cap as import). */
  file: File;
  delimiter: string;
  has_header: boolean;
  mappings: TableUpdateMapping[];
  match_mode: "key" | "order";
  source_key_index?: number | null;
  key_column_id?: number | null;
  case_insensitive_key?: boolean;
  skip_empty?: boolean;
}

export function updateTableCellsCsv(
  tableId: number,
  p: UpdateTableCsvParams,
): Promise<TableUpdateResult> {
  const fd = new FormData();
  fd.append("file", p.file);
  fd.append("delimiter", p.delimiter);
  fd.append("has_header", String(p.has_header));
  fd.append("mappings", JSON.stringify(p.mappings));
  fd.append("match_mode", p.match_mode);
  // Omit (rather than blank) the optional ints so FastAPI sees None.
  if (p.source_key_index != null)
    fd.append("source_key_index", String(p.source_key_index));
  if (p.key_column_id != null)
    fd.append("key_column_id", String(p.key_column_id));
  fd.append("case_insensitive_key", String(p.case_insensitive_key ?? false));
  fd.append("skip_empty", String(p.skip_empty ?? true));
  return api<TableUpdateResult>(`/library/tables/${tableId}/update-cells-csv`, {
    method: "POST",
    body: fd,
  });
}

// ----- Autotool (3rd publishing mode) -----

export interface AutotoolState {
  autotool_enabled: boolean;
  autotool_token: string | null;
  /** Relative public path, e.g. "/autotool/<token>.csv"; null when disabled. */
  csv_path: string | null;
}

/** Expose the table as a public CSV the Autotool proxy can fetch. */
export function enableAutotool(tableId: number): Promise<AutotoolState> {
  return api<AutotoolState>(`/library/tables/${tableId}/autotool`, {
    method: "POST",
  });
}

/** Remove the table from Autotool — invalidates the public link immediately. */
export function disableAutotool(tableId: number): Promise<AutotoolState> {
  return api<AutotoolState>(`/library/tables/${tableId}/autotool`, {
    method: "DELETE",
  });
}

/** Absolute public URL for the Autotool CSV. Resolves a relative API base
 *  (e.g. "/api" in production) against the current origin so the value is a
 *  full URL the external proxy can use. */
export function autotoolCsvUrl(token: string): string {
  const path = `${API_URL}/autotool/${token}.csv`;
  if (typeof window !== "undefined") {
    try {
      return new URL(path, window.location.origin).href;
    } catch {
      /* fall through to the raw path */
    }
  }
  return path;
}

/** Trigger a CSV download for the given table. */
export async function downloadCsv(tableId: number, filename: string): Promise<void> {
  const token = getToken();
  const res = await fetch(exportCsvUrl(tableId), {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
