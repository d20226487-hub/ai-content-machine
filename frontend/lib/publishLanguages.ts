/**
 * API client for the language-sync trigger + run history.
 *
 * Trigger: `POST /publish/languages/sync` accepts a list of targets and
 * persists the outcome as a `LanguageSyncRun` + per-target rows server-
 * side. The response now carries `run_id` so the UI can deep-link from
 * the just-finished sync to its detail page.
 *
 * History: list + detail endpoints feed the standalone reporting page
 * under `/publish/languages`.
 */
import { api } from "@/lib/api";

export interface LanguageSyncTarget {
  domain_name: string;
  languages: string[];
}

export type LanguageSyncSource = "bulk_modal" | "standalone";

export type LanguageSyncStatus = "queued" | "running" | "done";

/** Ack for an enqueued sync. The work runs in the background now, so the
 *  trigger returns only the new run id + its initial status — poll the run
 *  detail (or open its page) to watch progress and see per-site outcomes. */
export interface LanguageSyncTrigger {
  run_id: number;
  status: LanguageSyncStatus;
}

export function syncLanguages(
  targets: LanguageSyncTarget[],
  source: LanguageSyncSource = "bulk_modal",
): Promise<LanguageSyncTrigger> {
  // `api()` itself does JSON.stringify on the body field — pass the
  // object directly, not a pre-stringified payload. Double-stringifying
  // would send a JSON-encoded string and the backend would 422.
  return api<LanguageSyncTrigger>("/publish/languages/sync", {
    method: "POST",
    body: { targets, source },
  });
}

// ---- history ----

export interface LanguageSyncRun {
  id: number;
  created_at: string;
  created_by_id: number | null;
  created_by_name: string | null;
  source: string;
  status: LanguageSyncStatus;
  total_count: number;
  ok_count: number;
  fail_count: number;
  skip_count: number;
}

export interface LanguageSyncRunListResponse {
  items: LanguageSyncRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface LanguageSyncResultRow {
  id: number;
  domain_id: number | null;
  domain_name: string;
  languages: string[];
  /** 'pending' until the worker attempts this target, then 'done'. */
  state: "pending" | "done";
  ok: boolean;
  skipped: boolean;
  skip_reason: string | null;
  status_code: number | null;
  detail: string | null;
  elapsed_ms: number | null;
  created_at: string;
}

export interface LanguageSyncRunDetail extends LanguageSyncRun {
  started_at: string | null;
  finished_at: string | null;
  results: LanguageSyncResultRow[];
}

/** Re-attempt the failed targets of a finished run, in place. */
export function retryFailedRun(id: number): Promise<LanguageSyncRun> {
  return api<LanguageSyncRun>(`/publish/languages/runs/${id}/retry-failed`, {
    method: "POST",
  });
}

/** Re-enqueue an active run that stalled (worker died mid-flight). */
export function resumeRun(id: number): Promise<LanguageSyncRun> {
  return api<LanguageSyncRun>(`/publish/languages/runs/${id}/resume`, {
    method: "POST",
  });
}

export function listLanguageSyncRuns(
  page = 1,
  pageSize = 20,
): Promise<LanguageSyncRunListResponse> {
  return api<LanguageSyncRunListResponse>(
    `/publish/languages/runs?page=${page}&page_size=${pageSize}`,
  );
}

export function getLanguageSyncRun(id: number): Promise<LanguageSyncRunDetail> {
  return api<LanguageSyncRunDetail>(`/publish/languages/runs/${id}`);
}

// ---- name resolution (CSV import pre-flight) ----

export interface ResolvedKnownDomain {
  id: number;
  name: string;
  has_credentials: boolean;
  cms_type: string;
}

export interface ResolveNamesResult {
  known: ResolvedKnownDomain[];
  unknown: string[];
}

export function resolveDomainNames(
  names: string[],
): Promise<ResolveNamesResult> {
  return api<ResolveNamesResult>("/publish/languages/resolve", {
    method: "POST",
    body: { names },
  });
}
