import { api, getToken } from "./api";

/**
 * Background CSV export: queue a build, poll status, then download the
 * pre-built (gzipped) blob. Decouples export from a single long HTTP download
 * so large tables don't trip the front proxy/CDN response timeout.
 */

export type CsvExportStatus = "queued" | "running" | "done" | "failed";

export interface CsvExportJob {
  id: number;
  table_id: number | null;
  table_name: string;
  filename: string;
  status: CsvExportStatus;
  rows_total: number;
  rows_done: number;
  byte_size: number | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Queue a build; returns the job (status 'queued'). Poll getExportJob until done. */
export function createExportJob(tableId: number): Promise<CsvExportJob> {
  return api<CsvExportJob>(`/library/tables/${tableId}/export-jobs`, {
    method: "POST",
  });
}

export function getExportJob(jobId: number): Promise<CsvExportJob> {
  return api<CsvExportJob>(`/library/export-jobs/${jobId}`);
}

/**
 * Download the prepared blob. Uses fetch+blob (not a plain link) to carry the
 * bearer token. The server sends the stored bytes with Content-Encoding: gzip,
 * which the browser transparently decompresses, so the saved file is plain CSV.
 */
export async function downloadExportJob(
  jobId: number,
  filename: string,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/library/export-jobs/${jobId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`Download failed (HTTP ${res.status})`);
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
