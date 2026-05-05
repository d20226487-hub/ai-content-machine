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

export interface BulkRunSummary {
  id: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  table_id: number;
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
}

export interface BulkRunDetail extends BulkRunSummary {
  row_filter: RowFilter;
  selection: Record<string, unknown> | null;
  cell_filter: CellFilter;
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
}

export interface BulkPublishPayload {
  table_id: number;
  domain_id: number;
  profile_name?: string | null;
  language?: string | null;
  row_filter: RowFilter;
  selection?: Record<string, unknown> | null;
  cell_filter: CellFilter;
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
  save_mapping?: boolean;
}

export interface PublishMapping {
  field_to_column: Record<string, number>;
  back_fill: Record<string, number>;
  language: string | null;
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

function profileSegment(name: string | null | undefined): string {
  return !name ? "-" : encodeURIComponent(name);
}

export function getMapping(
  tableId: number,
  domainId: number,
  profileName: string | null,
) {
  return api<PublishMapping>(
    `/publish/mappings/${tableId}/${domainId}/${profileSegment(profileName)}`,
  );
}

export function clearMapping(
  tableId: number,
  domainId: number,
  profileName: string | null,
) {
  return api<void>(
    `/publish/mappings/${tableId}/${domainId}/${profileSegment(profileName)}`,
    { method: "DELETE" },
  );
}
