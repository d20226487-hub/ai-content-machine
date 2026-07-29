import { api } from "./api";

/** Masked config: the API key is never returned, only whether one is set. */
export interface AutotoolConfig {
  target_url: string | null;
  api_key_configured: boolean;
}

export interface AutotoolConfigUpdate {
  /** omit = unchanged, "" = clear, non-empty = set */
  target_url?: string | null;
  /** omit = unchanged, "" = clear, non-empty = set */
  api_key?: string | null;
}

export interface AutotoolTestResult {
  ok: boolean;
  status_code: number | null;
  detail: string;
  elapsed_ms: number | null;
}

export function getAutotoolConfig(): Promise<AutotoolConfig> {
  return api<AutotoolConfig>("/autotool/config");
}

export function saveAutotoolConfig(
  payload: AutotoolConfigUpdate,
): Promise<AutotoolConfig> {
  return api<AutotoolConfig>("/autotool/config", {
    method: "PUT",
    body: payload,
  });
}

export function testAutotoolConfig(): Promise<AutotoolTestResult> {
  return api<AutotoolTestResult>("/autotool/config/test", { method: "POST" });
}

// ----- shared tables + POST request preview -----

export interface AutotoolTableItem {
  id: number;
  name: string;
  /** Display name of the table's owner (creator); null if unset/deleted. */
  owner_name: string | null;
  autotool_token: string | null;
  csv_path: string | null;
  row_count: number;
  /** Count + names of the columns actually exposed to Autotool (the operator's
   *  selection, or all when none is set); column_count === columns.length. */
  column_count: number;
  columns: string[];
  updated_at: string;
}

export interface AutotoolTablesPage {
  items: AutotoolTableItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AutotoolDomainRequest {
  site: string;
  file: string;
  csv_path: string;
  /** 0-based row offset of this page within the domain. */
  start: number;
  /** the domain's full row count (across all pages). */
  total: number;
  /** rows in THIS page (<= page size). */
  row_count: number;
  body: {
    sites: string[];
    /** ACM does the row-split, so the proxy only needs the file. From the 2nd
     *  request, `id` (returned by the 1st) groups them into one import job. */
    data: { file: string; id?: string | number };
  };
}

export interface AutotoolPostPreview {
  method: string;
  url: string | null;
  headers: Record<string, string>;
  columns: { id: number; name: string }[];
  /** Required roles (domain/site, post_type, slug, status) not among the
   *  included columns; empty = ready to send. See missingRequiredColumns. */
  missing_required_columns: string[];
  /** Rows whose included `mode` column is "append" — Autotool appends the
   *  Content to existing WP content, so re-sending duplicates it. 0 = none. */
  append_row_count: number;
  /** This table already had a send run that delivered ≥1 item — a re-send would
   *  append a second time. Escalates the append warning. */
  previously_sent: boolean;
  site_column_id: number | null;
  detected_site_column_id: number | null;
  /** effective rows-per-request used to page the table (clamped server-side). */
  page_size: number;
  domain_count: number;
  /** total POSTs = sum over domains of ceil(rows / page size). */
  page_count: number;
  total_rows_matched: number;
  table_row_count: number;
  requests: AutotoolDomainRequest[];
  target_configured: boolean;
  api_key_configured: boolean;
}

/**
 * Columns Autotool's WordPress importer requires in every CSV, matched by
 * EXACT, case-insensitive header name (the `domain` role also accepts `site`).
 * Mirrors REQUIRED_AUTOTOOL_COLUMNS in backend/app/services/autotool_files.py —
 * keep the two lists in sync.
 */
export const AUTOTOOL_REQUIRED_COLUMNS: { label: string; names: string[] }[] = [
  { label: "domain", names: ["domain", "site"] },
  { label: "post_type", names: ["post_type"] },
  { label: "slug", names: ["slug"] },
  { label: "status", names: ["status"] },
];

/** Required Autotool roles NOT covered by `columnNames` (exact, case-insensitive,
 *  trimmed). Pass the names that will actually be in the CSV — i.e. the checked
 *  subset — so an unchecked required column is reported missing. */
export function missingRequiredColumns(columnNames: string[]): string[] {
  const present = new Set(columnNames.map((n) => n.trim().toLowerCase()));
  return AUTOTOOL_REQUIRED_COLUMNS.filter(
    (role) => !role.names.some((n) => present.has(n)),
  ).map((role) => role.label);
}

export function listSharedTables(
  page = 1,
  pageSize = 20,
): Promise<AutotoolTablesPage> {
  return api<AutotoolTablesPage>(
    `/autotool/tables?page=${page}&page_size=${pageSize}`,
  );
}

export function getPostPreview(
  tableId: number,
  siteColumnId?: number | null,
  pageSize?: number | null,
): Promise<AutotoolPostPreview> {
  const qs = new URLSearchParams();
  if (siteColumnId != null) qs.set("site_column_id", String(siteColumnId));
  if (pageSize != null) qs.set("page_size", String(pageSize));
  const s = qs.toString();
  return api<AutotoolPostPreview>(
    `/autotool/tables/${tableId}/post-preview${s ? `?${s}` : ""}`,
  );
}

// ----- send runs (background, with a progress page) -----

export type AutotoolRunStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

export type AutotoolItemStatus =
  | "queued"
  | "sending"
  | "sent"
  | "failed"
  | "skipped";

export interface AutotoolRun {
  id: number;
  table_id: number | null;
  table_name: string;
  target_url: string;
  page_size: number;
  status: AutotoolRunStatus;
  total: number;
  sent: number;
  failed: number;
  skipped: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AutotoolRunItem {
  id: number;
  site: string;
  start: number;
  total: number;
  status: AutotoolItemStatus;
  /** the proxy id for this item's site (null until its leader captures it). */
  external_id: string | number | null;
  status_code: number | null;
  detail: string | null;
  response_snippet: string | null;
  elapsed_ms: number | null;
  created_at: string;
}

export interface AutotoolRunsPage {
  items: AutotoolRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface AutotoolRunDetail extends AutotoolRun {
  site_column_id: number | null;
  error: string | null;
  items: AutotoolRunItem[];
  items_total: number;
  items_page: number;
  items_page_size: number;
}

/** Create a background send run and enqueue it. Publishes to live sites — the
 *  caller must confirm first, then redirect to the run's progress page. */
export function createAutotoolRun(
  tableId: number,
  siteColumnId?: number | null,
  pageSize?: number | null,
  acknowledgeAppend = false,
): Promise<AutotoolRunDetail> {
  return api<AutotoolRunDetail>("/autotool/runs", {
    method: "POST",
    body: {
      table_id: tableId,
      site_column_id: siteColumnId ?? null,
      page_size: pageSize ?? null,
      acknowledge_append: acknowledgeAppend,
    },
  });
}

export function listAutotoolRuns(
  page = 1,
  pageSize = 20,
): Promise<AutotoolRunsPage> {
  return api<AutotoolRunsPage>(
    `/autotool/runs?page=${page}&page_size=${pageSize}`,
  );
}

export function getAutotoolRun(
  runId: number,
  page = 1,
  pageSize = 50,
): Promise<AutotoolRunDetail> {
  return api<AutotoolRunDetail>(
    `/autotool/runs/${runId}?page=${page}&page_size=${pageSize}`,
  );
}

export function cancelAutotoolRun(runId: number): Promise<AutotoolRunDetail> {
  return api<AutotoolRunDetail>(`/autotool/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function retryFailedAutotoolRun(
  runId: number,
): Promise<AutotoolRunDetail> {
  return api<AutotoolRunDetail>(`/autotool/runs/${runId}/retry-failed`, {
    method: "POST",
  });
}
