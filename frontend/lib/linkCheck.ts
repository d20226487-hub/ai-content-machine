import { api } from "./api";

// Mirrors backend app/schemas/bulk.py (link checker section).

export type LinkCheckStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";
export type LinkProblem = "omitted" | "hallucinated" | "broken" | "ok";
/** In-place AI re-verify outcome. null = untouched (never fixed). */
export type LinkResolution = "solved" | "unsolved";

/** Per-type link treatment for the translation-links mode. */
export type LinkTreatment = "skip" | "localize";

/** Config for the 3rd mode — translation links. Bulk textareas
 * (internal_domains / product_patterns / exceptions) are parsed server-side. */
export interface TranslationCheckConfig {
  original_column_id: number;
  translated_column_id: number;
  lang_column_id: number;
  /** Columns holding each row's own site domain(s) → internal links. */
  internal_domain_column_ids: number[];
  /** Product domain(s) (comma/space separated) → product links. */
  product_domain: string;
  /** One "language, page" per line; the page keeps its root URL. */
  exceptions: string;
  internal_treatment: LinkTreatment;
  external_treatment: LinkTreatment;
}

export interface LinkCheckRequest {
  /** Output columns to scan (at least one) — omitted in translation mode. */
  column_ids?: number[];
  /** Expected-link columns (union); required when check_juxtapose is true. */
  expected_column_ids?: number[];
  check_juxtapose?: boolean;
  check_crawl?: boolean;
  /** Also record healthy links as rows (full per-link inventory). */
  include_ok?: boolean;
  /** When set, runs the translation-links mode instead of the checks above. */
  translation?: TranslationCheckConfig;
}

export interface LinkCheckRun {
  id: number;
  table_id: number;
  name: string | null;
  status: LinkCheckStatus;
  column_ids: number[];
  expected_column_ids: number[];
  check_juxtapose: boolean;
  check_crawl: boolean;
  include_ok: boolean;
  total_links: number;
  crawled: number;
  ok_count: number;
  broken_count: number;
  omitted_count: number;
  hallucinated_count: number;
  error: string | null;
  created_by_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** Non-null only for translation-mode runs. */
  translation_config?: Record<string, unknown> | null;
}

export interface LinkViolation {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  problem: LinkProblem;
  link: string;
  detail_code: string | null;
  status_code: number | null;
  /** null = untouched; set by the in-place re-verify after an AI fix. */
  resolution: LinkResolution | null;
}

export interface LinkCheckRunDetail extends LinkCheckRun {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_violations: number;
  status_codes_present: number[];
  /** Crawl status-class breakdown (unique-URL based) for the overview. */
  status_2xx: number;
  status_3xx: number;
  status_404: number;
  status_5xx: number;
  items: LinkViolation[];
}

export interface LinkViolationFilters {
  problem?: LinkProblem | "";
  status_code?: number | null;
  q?: string;
  /** When true, `q` is a "does not contain" filter. */
  q_negate?: boolean;
  /** solved | unsolved | untouched */
  resolution?: LinkResolution | "untouched" | "";
}

export function startLinkCheck(
  tableId: number,
  req: LinkCheckRequest,
): Promise<LinkCheckRun> {
  return api<LinkCheckRun>(`/library/tables/${tableId}/link-check`, {
    method: "POST",
    body: req,
  });
}

export function listLinkCheckRuns(
  tableId: number,
): Promise<LinkCheckRun[]> {
  return api<LinkCheckRun[]>(`/library/tables/${tableId}/link-check-runs`);
}

export function getLinkCheckRun(
  runId: number,
  page = 1,
  pageSize = 25,
  filters: LinkViolationFilters = {},
): Promise<LinkCheckRunDetail> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.problem) sp.set("problem", filters.problem);
  if (filters.status_code != null) sp.set("status_code", String(filters.status_code));
  if (filters.q && filters.q.trim()) {
    sp.set("q", filters.q.trim());
    if (filters.q_negate) sp.set("q_negate", "true");
  }
  if (filters.resolution) sp.set("resolution", filters.resolution);
  return api<LinkCheckRunDetail>(
    `/library/link-check-runs/${runId}?${sp.toString()}`,
  );
}

export interface TranslationTableRow {
  row_id: number;
  row_position: number;
  original: string[];
  expected: string[];
  translation: string[];
  mismatches: string[];
}

export interface TranslationTableResponse {
  page: number;
  page_size: number;
  total_rows: number;
  items: TranslationTableRow[];
}

/** The 4-column raw breakdown for a translation run, paginated by row
 *  (computed on demand — nothing is materialized into the bulk table). */
export function getTranslationTable(
  runId: number,
  page = 1,
  pageSize = 25,
): Promise<TranslationTableResponse> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return api<TranslationTableResponse>(
    `/library/link-check-runs/${runId}/translation-table?${sp.toString()}`,
  );
}

export function cancelLinkCheckRun(runId: number): Promise<LinkCheckRun> {
  return api<LinkCheckRun>(`/library/link-check-runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function resumeLinkCheckRun(runId: number): Promise<LinkCheckRun> {
  return api<LinkCheckRun>(`/library/link-check-runs/${runId}/resume`, {
    method: "POST",
  });
}

export function renameLinkCheckRun(
  runId: number,
  name: string | null,
): Promise<LinkCheckRun> {
  return api<LinkCheckRun>(`/library/link-check-runs/${runId}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteLinkCheckRun(runId: number): Promise<void> {
  return api<void>(`/library/link-check-runs/${runId}`, { method: "DELETE" });
}
