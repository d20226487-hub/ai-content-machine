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

export function getTable(id: number): Promise<BulkTable> {
  return api<BulkTable>(`/library/tables/${id}`);
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

export interface GenerateRequestPayload {
  row_ids?: number[];
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

// ----- CSV -----

export interface ImportCsvPayload {
  name: string;
  csv_text: string;
  delimiter?: string;
  has_header?: boolean;
}

export function importCsv(p: ImportCsvPayload): Promise<BulkTable> {
  return api<BulkTable>("/library/tables/import-csv", {
    method: "POST",
    body: p,
  });
}

/** Build a download URL with the auth token forwarded. Used for CSV export. */
export function exportCsvUrl(tableId: number): string {
  // Browsers won't add Authorization automatically; we trigger this via fetch+blob.
  return `${API_URL}/library/tables/${tableId}/export.csv`;
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
