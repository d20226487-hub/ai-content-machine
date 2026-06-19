import { api } from "@/lib/api";

export type BulkRunStatus =
  | "queued"
  | "running"
  | "paused"
  | "cancelled"
  | "done"
  | "failed";

export type RowFilter = "all" | "selected" | "range";
export type CellFilter = "all" | "unpublished" | "failed";
export type PublishMode = "single" | "multi";
export type PublishOperation = "create" | "update" | "upsert";
export type PublishLookupKind = "id" | "slug";
/** What to do in Create mode when a row's slug already exists on the target. */
export type OnSlugConflict = "create" | "skip" | "update";

/** Built-in Custom CMS page type. 'ordinary' uses the domain's own endpoint +
 *  body_template; 'match' pins the hardcoded /add-sport-page endpoint + the
 *  sport field set. WordPress runs ignore this. */
export type CustomPageType = "ordinary" | "match";

/** The endpoints a 'match' run posts to — Create and Update hit different
 *  URLs. Mirrors the backend constant in app/cms/custom_page_types.py; kept
 *  here only for display (the request is built server-side). */
export const MATCH_PAGE_ENDPOINT = "/add-sport-page"; // create
export const MATCH_UPDATE_ENDPOINT = "/update-sport-page"; // update

/** Mappable field slots for a 'match' run. Mirrors the match body_template
 *  placeholders in app/cms/custom_page_types.py. ``lang`` IS included (same as
 *  ordinary Custom pages) so a per-row language column maps straight to it —
 *  without it, every row falls back to the run-level language. The run-level
 *  language picker / "Language column" control still work as a fallback when
 *  ``lang`` is left unmapped. (``action``/``id`` are driven by the operation
 *  toggle + lookup panel, not field slots.)
 *
 *  The bulk modal renders these as mapping slots regardless of which domain a
 *  row resolves to — so 'match' isn't subject to the "multi mode reads one
 *  canonical domain's template" behavior that 'ordinary' has. */
export const MATCH_PAGE_FIELDS = [
  "lang",
  "slug",
  "title",
  "seo_description",
  "date",
  "time",
  "venue",
  "group",
  "odds_home",
  "odds_draw",
  "odds_away",
  "content",
  // 'top' holds "true"/"false" text in the table; the backend sends it as a
  // real JSON boolean (see boolean_fields in app/cms/custom_page_types.py).
  "top",
] as const;

export interface BulkRunSummary {
  id: number;
  name: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  table_id: number;
  mode: PublishMode;
  domain_id: number | null;
  domain_name: string | null;
  table_name: string | null;
  profile_name: string | null;
  language: string | null;
  status: BulkRunStatus;
  total: number;
  done: number;
  failed: number;
  skipped: number;
  error: string | null;
  created_by_id: number | null;
  operation: PublishOperation;
  lookup_kind: PublishLookupKind | null;
  lookup_column_id: number | null;
  language_column_id: number | null;
  on_slug_conflict: OnSlugConflict;
  custom_page_type: CustomPageType;
}

export interface ByDomainStat {
  domain_id: number | null;
  domain_name: string | null;
  total: number;
  posted: number;
  failed: number;
}

export interface BulkRunDetail extends BulkRunSummary {
  row_filter: RowFilter;
  selection: Record<string, unknown> | null;
  cell_filter: CellFilter;
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
  domain_column_id: number | null;
  profile_column_id: number | null;
  by_domain: ByDomainStat[];
}

export interface BulkPublishPayload {
  table_id: number;
  mode: PublishMode;

  // single mode
  domain_id?: number | null;
  profile_name?: string | null;

  // multi mode
  domain_column_id?: number | null;
  profile_column_id?: number | null;
  /** Multi mode only: per-row language. When set, each row's cell must
   *  hold a value that matches the resolved domain's `languages[]`.
   *  Empty cells fail the row. */
  language_column_id?: number | null;

  language?: string | null;
  row_filter: RowFilter;
  selection?: Record<string, unknown> | null;
  cell_filter: CellFilter;
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
  save_mapping?: boolean;

  /** "create" (POST new posts) or "update" (PATCH existing posts). Default "create".
   *  Update is WP-only. */
  operation?: PublishOperation;
  /** Required when operation="update". "id" treats the cell as a numeric post id;
   *  "slug" looks up the post via /wp-json/wp/v2/{type}?slug=… */
  lookup_kind?: PublishLookupKind | null;
  /** Required when operation="update". Column whose cells hold the lookup value. */
  lookup_column_id?: number | null;
  /** Create-mode only. "create" (default) = always POST and let WP auto-suffix.
   *  "skip" = if a post with the same slug exists in the row's language, log
   *  the row as skipped. "update" = PATCH the existing post instead.
   *  Requires `slug` to be in field_to_column. */
  on_slug_conflict?: OnSlugConflict;
  /** Custom CMS built-in page type. 'match' pins /add-sport-page + the sport
   *  field set; 'ordinary' (default) uses the domain's own config. */
  custom_page_type?: CustomPageType;
}

export interface PublishMapping {
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
  language: string | null;
  domain_column_id?: number | null;
  profile_column_id?: number | null;
  language_column_id?: number | null;
  operation?: PublishOperation;
  lookup_kind?: PublishLookupKind | null;
  lookup_column_id?: number | null;
  on_slug_conflict?: OnSlugConflict;
  custom_page_type?: CustomPageType;
}

export interface BulkRunListResponse {
  items: BulkRunSummary[];
  total: number;
  page: number;
  page_size: number;
}

export function createBulkRun(payload: BulkPublishPayload) {
  return api<BulkRunDetail>("/publish/bulk", { method: "POST", body: payload });
}

export function listBulkRuns(opts: {
  page?: number;
  page_size?: number;
  status?: BulkRunStatus;
  table_id?: number;
  domain_id?: number;
} = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(opts)) {
    if (v === undefined || v === null) continue;
    const s = String(v);
    if (!s) continue;
    p.set(k, s);
  }
  const qs = p.toString();
  return api<BulkRunListResponse>(`/publish/runs${qs ? `?${qs}` : ""}`);
}

export function getBulkRun(id: number) {
  return api<BulkRunDetail>(`/publish/runs/${id}`);
}

export function pauseBulkRun(id: number) {
  return api<BulkRunDetail>(`/publish/runs/${id}/pause`, { method: "POST" });
}

export function resumeBulkRun(id: number) {
  return api<BulkRunDetail>(`/publish/runs/${id}/resume`, { method: "POST" });
}

export function cancelBulkRun(id: number) {
  return api<BulkRunDetail>(`/publish/runs/${id}/cancel`, { method: "POST" });
}

export function rerunFailedRows(id: number) {
  return api<BulkRunDetail>(`/publish/runs/${id}/rerun-failed`, {
    method: "POST",
  });
}

export function deleteBulkRun(id: number) {
  return api<void>(`/publish/runs/${id}`, { method: "DELETE" });
}

export function renameBulkRun(id: number, name: string | null) {
  return api<BulkRunDetail>(`/publish/runs/${id}`, {
    method: "PATCH",
    body: { name },
  });
}

export function clearCompletedBulkRuns() {
  return api<{ deleted: number }>("/publish/runs/completed", {
    method: "DELETE",
  });
}

function profileSegment(name: string | null | undefined): string {
  return !name ? "-" : encodeURIComponent(name);
}

export function getMappingSingle(
  tableId: number,
  domainId: number,
  profileName: string | null,
) {
  return api<PublishMapping>(
    `/publish/mappings/${tableId}/single/${domainId}/${profileSegment(profileName)}`,
  );
}

export function clearMappingSingle(
  tableId: number,
  domainId: number,
  profileName: string | null,
) {
  return api<void>(
    `/publish/mappings/${tableId}/single/${domainId}/${profileSegment(profileName)}`,
    { method: "DELETE" },
  );
}

export function getMappingMulti(tableId: number) {
  return api<PublishMapping>(`/publish/mappings/${tableId}/multi`);
}

export function clearMappingMulti(tableId: number) {
  return api<void>(`/publish/mappings/${tableId}/multi`, { method: "DELETE" });
}
