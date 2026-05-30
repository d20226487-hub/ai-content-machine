import { api } from "./api";

// Mirrors backend app/schemas/bulk.py (link checker section).

export type LinkCheckStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";
export type LinkProblem = "omitted" | "hallucinated" | "broken" | "ok";

export interface LinkCheckRequest {
  /** Output columns to scan (at least one). */
  column_ids: number[];
  /** Expected-link columns (union); required when check_juxtapose is true. */
  expected_column_ids: number[];
  check_juxtapose: boolean;
  check_crawl: boolean;
  /** Also record healthy links as rows (full per-link inventory). */
  include_ok: boolean;
}

export interface LinkCheckRun {
  id: number;
  table_id: number;
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
}

export interface LinkCheckRunDetail extends LinkCheckRun {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_violations: number;
  status_codes_present: number[];
  items: LinkViolation[];
}

export interface LinkViolationFilters {
  problem?: LinkProblem | "";
  status_code?: number | null;
  q?: string;
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
  if (filters.q && filters.q.trim()) sp.set("q", filters.q.trim());
  return api<LinkCheckRunDetail>(
    `/library/link-check-runs/${runId}?${sp.toString()}`,
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
