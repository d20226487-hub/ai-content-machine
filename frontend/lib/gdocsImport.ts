import { api, ApiError, getToken } from "./api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type GdocsImportStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

/** Mirrors backend ``GdocsImportRunRead`` (payload deliberately omitted). */
export interface GdocsImportRun {
  id: number;
  status: GdocsImportStatus;
  table_name: string;
  target_folder_id: number | null;
  mode: string | null;
  /** Per-import AI override (null = first-enabled provider + its default model). */
  provider_code: string | null;
  model: string | null;
  result_table_id: number | null;
  total_docs: number;
  docs_done: number;
  docs_failed: number;
  total_pages: number;
  pages_matched: number;
  pages_unmatched: number;
  /** Planned Structure entries across all sites (coverage denominator). */
  total_structure_pages: number;
  rows_built: number;
  warnings: string[];
  error: string | null;
  created_by_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_progress_at: string | null;
}

/**
 * Upload the Apps-Script JSON export and queue a background import.
 *
 * Uses a raw ``fetch`` rather than the shared ``api`` helper because the body
 * is ``multipart/form-data`` (the helper always JSON-encodes + sets a JSON
 * content-type). Returns the freshly-created run (status ``queued``); poll
 * :func:`getGdocsRun` for progress.
 */
export async function importGdocs(args: {
  file: File;
  name: string;
  folderId?: number | null;
  /** Optional AI override. Omit both to use the workspace default provider. */
  providerCode?: string | null;
  model?: string | null;
}): Promise<GdocsImportRun> {
  const form = new FormData();
  form.append("file", args.file);
  form.append("name", args.name);
  if (args.folderId != null) form.append("folder_id", String(args.folderId));
  if (args.providerCode) form.append("provider_code", args.providerCode);
  if (args.model) form.append("model", args.model);

  const token = getToken();
  const res = await fetch(`${API_URL}/library/import/gdocs`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });

  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const message =
      (data as { detail?: string } | undefined)?.detail ??
      `Import failed (${res.status})`;
    throw new ApiError(res.status, message, data);
  }
  return data as GdocsImportRun;
}

export function listGdocsRuns(limit = 50): Promise<GdocsImportRun[]> {
  return api<GdocsImportRun[]>(`/library/import/gdocs-runs?limit=${limit}`);
}

export function getGdocsRun(runId: number): Promise<GdocsImportRun> {
  return api<GdocsImportRun>(`/library/import/gdocs-runs/${runId}`);
}

export function cancelGdocsRun(runId: number): Promise<GdocsImportRun> {
  return api<GdocsImportRun>(`/library/import/gdocs-runs/${runId}/cancel`, {
    method: "POST",
  });
}

/**
 * Delete an import run from history (204). Backend rejects active runs with a
 * 409 — cancel first. Only the history record goes; the table it built stays.
 */
export function deleteGdocsRun(runId: number): Promise<void> {
  return api<void>(`/library/import/gdocs-runs/${runId}`, {
    method: "DELETE",
  });
}
