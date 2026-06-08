import { api } from "./api";
import type { LinkFixRun } from "./linkFix";

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
  /** One "domain, lang" per line — the language a product site serves at its
   *  root (no subfolder), so the default language isn't given a /<lang>/ path. */
  product_default_langs: string;
  internal_treatment: LinkTreatment;
  external_treatment: LinkTreatment;
}

/** The parsed translation config as STORED on a run (lists/maps, not the raw
 *  textareas). Used to prefill the setup form when rerunning with tweaks. */
export interface StoredTranslationConfig {
  original_column_id: number;
  translated_column_id: number;
  lang_column_id: number;
  internal_domain_column_ids?: number[];
  product_domains?: string[];
  exceptions?: { lang: string; page: string }[];
  product_default_langs?: Record<string, string>;
  internal_treatment?: LinkTreatment;
  external_treatment?: LinkTreatment;
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
  /** Optional link-type classification (product / internal / external) for the
   *  findings. product_domain is comma/space/newline-separated; internal
   *  domains come per-row from the chosen column(s). */
  product_domain?: string;
  internal_domain_column_ids?: number[];
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
  /** Non-null when the crawl/juxtapose run classified links by type — the run
   *  page shows the product/internal/external filter when it's set. */
  classify_config?: Record<string, unknown> | null;
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
  link_type?: LinkTypeCategory | null;
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
  /** product | internal | external */
  link_type?: LinkTypeFilter | "";
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
  if (filters.link_type) sp.set("link_type", filters.link_type);
  return api<LinkCheckRunDetail>(
    `/library/link-check-runs/${runId}?${sp.toString()}`,
  );
}

/** How a translation link compares to the expected links. */
export type TranslationLinkKind = "ok" | "discrepancy" | "invented";

/** Link type of the original behind an aligned row (drives the type filter).
 *  Made-up links are bucketed into one of these by their own host. */
export type LinkTypeCategory = "product" | "internal" | "external";

export interface TranslationLinkTag {
  url: string;
  kind: TranslationLinkKind;
  /** The user bulk-dismissed this error. */
  dismissed: boolean;
  /** A wrong link a fix/replace run has since corrected — shown struck through
   *  in the overview, and not selectable. */
  resolved?: boolean;
  /** The link this one SHOULD have been (set only for a discrepancy paired to
   *  an expected link). Used to underline just the drifting part. */
  expected?: string | null;
  /** The original (source) link this discrepancy was paired to — shown aligned
   *  beside it in the discrepancy-only view. */
  original?: string | null;
  link_type?: LinkTypeCategory | null;
}

/** An expected link paired with the wrong translation link it should have
 *  been (wrong null = correct/omitted; expected null = invented link). */
export interface AlignedRow {
  expected: string | null;
  wrong: TranslationLinkTag | null;
  link_type: LinkTypeCategory;
}

export interface TranslationTableRow {
  row_id: number;
  row_position: number;
  lang: string;
  original: string[];
  translation: TranslationLinkTag[];
  aligned: AlignedRow[];
  has_discrepancy: boolean;
}

export interface TranslationTableResponse {
  page: number;
  page_size: number;
  total_rows: number;
  items: TranslationTableRow[];
}

/** active = rows with live, unsolved errors; solved = rows whose errors a
 *  fix/replace run already corrected (struck through); dismissed = rows with
 *  dismissed errors (to restore); all = every row with links. */
export type TranslationTableView = "active" | "all" | "dismissed" | "solved";

/** Link-type filter. "all" = no filter. */
export type LinkTypeFilter = "all" | LinkTypeCategory;

/** The raw breakdown for a translation run, paginated by row (computed on
 *  demand — nothing is materialized into the bulk table). */
export function getTranslationTable(
  runId: number,
  page = 1,
  pageSize = 25,
  view: TranslationTableView = "active",
  linkType: LinkTypeFilter = "all",
): Promise<TranslationTableResponse> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    view,
    link_type: linkType,
  });
  return api<TranslationTableResponse>(
    `/library/link-check-runs/${runId}/translation-table?${sp.toString()}`,
  );
}

/** A dismissable error: which row + which link. */
export interface DismissItem {
  row_id: number;
  link: string;
}

export function dismissTranslationErrors(
  runId: number,
  items: DismissItem[],
): Promise<void> {
  return api<void>(
    `/library/link-check-runs/${runId}/translation-table/dismiss`,
    { method: "POST", body: { items } },
  );
}

export function restoreTranslationErrors(
  runId: number,
  items: DismissItem[],
): Promise<void> {
  return api<void>(
    `/library/link-check-runs/${runId}/translation-table/restore`,
    { method: "POST", body: { items } },
  );
}

/** Replace each selected wrong translation link with its expected link,
 *  in-place in the translated-content cell. Recorded as a revertable
 *  link-fix run (method='replace'); returns that run so the caller can open
 *  its detail page alongside the AI corrections. */
export function replaceTranslationLinks(
  runId: number,
  items: DismissItem[],
): Promise<LinkFixRun> {
  return api<LinkFixRun>(
    `/library/link-check-runs/${runId}/translation-table/replace`,
    { method: "POST", body: { items } },
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
