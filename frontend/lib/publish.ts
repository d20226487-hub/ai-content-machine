import { api } from "@/lib/api";

export type JobStatus = "queued" | "posting" | "posted" | "failed" | "skipped";
export type SourceKind = "single" | "bulk_cell";

export interface PublishJob {
  id: number;
  created_at: string;
  finished_at: string | null;
  domain_id: number | null;
  domain_name: string | null;
  source_kind: SourceKind;
  source_ref: Record<string, unknown> | null;
  status: JobStatus;
  language: string | null;
  cms_post_id: string | null;
  cms_post_url: string | null;
  /**
   * Upstream HTTP status code (100–599). NULL for rows that landed
   * before backend migration 0026 (no way to backfill), or for rows
   * where the request never reached an HTTP layer (e.g. an SSRF
   * pre-flight rejection). Surfaces in the run-detail table next to
   * the status badge so a "posted 201" vs "failed 403" is visible at a
   * glance without parsing the error string.
   */
  status_code: number | null;
  error: string | null;
  warnings: string[] | null;
  profile_name: string | null;
  created_by_id: number | null;
  /** The slug actually sent to the CMS (post-normalization). null when no slug
   *  field was sent (e.g. an empty slug dropped from the body). */
  slug: string | null;
}

export interface PublishJobDetail extends PublishJob {
  payload_sent: Record<string, unknown> | null;
  response_json: Record<string, unknown> | null;
  /** Copy-pasteable curl reproducing the exact request sent for this row
   *  (method + URL + headers with auth masked + the real JSON body). null
   *  when nothing was sent yet or the target can't be resolved. */
  curl_preview: string | null;
}

export interface PublishJobListResponse {
  items: PublishJob[];
  total: number;
  page: number;
  page_size: number;
}

export interface PublishSinglePayload {
  domain_id: number;
  fields: Record<string, unknown>;
  language?: string | null;
  profile_name?: string | null;
  source_ref?: Record<string, unknown> | null;
}

export function publishSingle(payload: PublishSinglePayload) {
  return api<PublishJobDetail>("/publish/single", { method: "POST", body: payload });
}

export function listPublishJobs(opts: {
  page?: number;
  page_size?: number;
  status?: JobStatus;
  source_kind?: "single" | "bulk_row" | "bulk_cell";
  domain_id?: number;
  run_id?: number;
  generation_id?: number;
} = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(opts)) {
    if (v === undefined || v === null) continue;
    const s = String(v);
    if (!s) continue;
    p.set(k, s);
  }
  const qs = p.toString();
  return api<PublishJobListResponse>(`/publish/jobs${qs ? `?${qs}` : ""}`);
}

export function getPublishJob(id: number) {
  return api<PublishJobDetail>(`/publish/jobs/${id}`);
}

export function deletePublishJob(id: number) {
  return api<void>(`/publish/jobs/${id}`, { method: "DELETE" });
}

export function clearCompletedPublishJobs(opts: {
  source_kind?: "single" | "bulk_row" | "bulk_cell";
} = {}) {
  const qs = opts.source_kind ? `?source_kind=${opts.source_kind}` : "";
  return api<{ deleted: number }>(`/publish/jobs/completed${qs}`, {
    method: "DELETE",
  });
}

export interface PublishDefaults {
  requests_per_minute: number;
  max_concurrency: number;
  inter_request_delay_ms: number;
  retry_max_attempts: number;
  backoff_base_ms: number;
  backoff_jitter_ms: number;
  respect_retry_after: boolean;
}

export function getPublishDefaults() {
  return api<PublishDefaults>("/publish/defaults");
}

export function setPublishDefaults(payload: PublishDefaults) {
  return api<PublishDefaults>("/publish/defaults", {
    method: "PUT",
    body: payload,
  });
}
