import { api } from "./api";

/**
 * Bulk Custom-CMS cache-clear runs. Only Custom-CMS domains are processed;
 * WordPress / unavailable domains in a selection are excluded server-side and
 * reported via ``skipped_unsupported``.
 */

// New runs are always "clear" (warming was removed — it overloaded sites).
// "warm" / "clear_and_warm" remain only so historical runs still render.
export type CacheAction = "clear" | "warm" | "clear_and_warm";

export type CacheRunStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

export type CacheItemStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "skipped";

export interface DomainCacheRun {
  id: number;
  action: CacheAction;
  status: CacheRunStatus;
  total: number;
  done: number;
  failed: number;
  skipped: number;
  /** Selected domains excluded because they aren't Custom CMS (or are gone). */
  skipped_unsupported: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DomainCacheRunItem {
  id: number;
  domain_id: number | null;
  domain_name: string;
  base_url: string;
  status: CacheItemStatus;
  clear_status_code: number | null;
  warm_status_code: number | null;
  detail: string | null;
  elapsed_ms: number | null;
  created_at: string;
}

export interface DomainCacheRunsPage {
  items: DomainCacheRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface DomainCacheRunDetail extends DomainCacheRun {
  error: string | null;
  items: DomainCacheRunItem[];
  items_total: number;
  items_page: number;
  items_page_size: number;
}

/** Create a background cache-clear run and enqueue it. Returns the run's detail
 *  so the caller can redirect to its progress page. (Clear is the only action —
 *  warming was removed.) */
export function createDomainCacheRun(
  domainIds: number[],
): Promise<DomainCacheRunDetail> {
  return api<DomainCacheRunDetail>("/domains/cache/runs", {
    method: "POST",
    body: { domain_ids: domainIds, action: "clear" },
  });
}

export function listDomainCacheRuns(
  page = 1,
  pageSize = 20,
): Promise<DomainCacheRunsPage> {
  return api<DomainCacheRunsPage>(
    `/domains/cache/runs?page=${page}&page_size=${pageSize}`,
  );
}

export function getDomainCacheRun(
  runId: number,
  page = 1,
  pageSize = 50,
): Promise<DomainCacheRunDetail> {
  return api<DomainCacheRunDetail>(
    `/domains/cache/runs/${runId}?page=${page}&page_size=${pageSize}`,
  );
}

export function cancelDomainCacheRun(
  runId: number,
): Promise<DomainCacheRunDetail> {
  return api<DomainCacheRunDetail>(`/domains/cache/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function retryFailedDomainCacheRun(
  runId: number,
): Promise<DomainCacheRunDetail> {
  return api<DomainCacheRunDetail>(`/domains/cache/runs/${runId}/retry-failed`, {
    method: "POST",
  });
}
