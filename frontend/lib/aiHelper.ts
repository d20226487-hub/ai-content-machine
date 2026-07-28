import { api } from "./api";

/** Legacy v1 run-level mode (still returned for old runs). */
export type AiHelperMode = "read" | "edit";
/** v1.1 fan-out engine. */
export type AiHelperEngine = "structured" | "per_output";
/** Per-output mode: produce new content, or rewrite the column in place. */
export type AiHelperOutputMode = "write" | "edit";
export type AiHelperStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

export interface AiHelperOutput {
  column_id: number;
  mode: AiHelperOutputMode;
  /** JSON key routed to this column (structured engine). */
  key: string;
  /** This output's own prompt (per_output engine). */
  prompt: string;
  /** Column name (populated by the backend on read). */
  name?: string;
}

export interface AiHelperCell {
  id: number;
  row_id: number;
  row_position: number;
  column_id: number;
  state: "pending" | "done" | "failed" | "skipped";
  old_value: string | null;
  new_value: string | null;
  error: string | null;
}

export interface AiHelperRunDetail {
  id: number;
  table_id: number;
  status: AiHelperStatus;
  mode: AiHelperMode;
  engine: AiHelperEngine;
  name: string | null;
  target_column_id: number | null;
  total: number;
  done: number;
  failed: number;
  skipped: number;
  reverted_at: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  prompt: string;
  variable_map: Record<string, number>;
  outputs: AiHelperOutput[];
  provider_code: string | null;
  model: string | null;
  input_scope: string;
  input_pct: number | null;
  error: string | null;
  items: AiHelperCell[];
  items_total: number;
  items_page: number;
  items_page_size: number;
}

/** Light run row for the tool-page history list (no cells). */
export interface AiHelperRunListItem {
  id: number;
  status: AiHelperStatus;
  engine: AiHelperEngine;
  mode: AiHelperMode;
  name: string | null;
  total: number;
  done: number;
  failed: number;
  skipped: number;
  reverted_at: string | null;
  created_at: string;
}

export interface AiHelperPreview {
  matched_rows: number;
  est_calls: number;
  provider_code: string | null;
  model: string | null;
  est_cost_usd: number | null;
  est_input_tokens_avg: number | null;
  provider_configured: boolean;
}

export interface AiHelperRunCreate {
  engine: AiHelperEngine;
  prompt: string;
  prompt_id?: number | null;
  name?: string | null;
  variable_map: Record<string, number>;
  outputs: AiHelperOutput[];
  provider_code?: string | null;
  model?: string | null;
  max_output_tokens?: number | null;
  input_scope: "full" | "first_pct";
  input_pct?: number | null;
  slice_column_id?: number | null;
  row_ids: number[];
}

/** Slug a column name into a JSON key: lowercase, non-alphanumerics → "_". */
export function slugifyKey(name: string): string {
  const base = (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return base || "field";
}

/** Slug `name`, suffixing _2, _3… so it doesn't collide with `taken`. */
export function uniqueKey(name: string, taken: Set<string>): string {
  const base = slugifyKey(name);
  if (!taken.has(base)) return base;
  let i = 2;
  while (taken.has(`${base}_${i}`)) i += 1;
  return `${base}_${i}`;
}

/** Same {{var}} rule as the backend (prompts.py): letters/digits/_-.  + internal
 *  spaces, outer whitespace trimmed, internal runs collapsed. */
const _VAR = /\{\{\s*([A-Za-z_][\w.\- ]*?)\s*\}\}/g;

export function extractVariables(prompt: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  let m: RegExpExecArray | null;
  _VAR.lastIndex = 0;
  while ((m = _VAR.exec(prompt)) !== null) {
    const name = m[1].replace(/\s+/g, " ").trim();
    if (name && !seen.has(name)) {
      seen.add(name);
      out.push(name);
    }
  }
  return out;
}

export function createAiHelperRun(
  tableId: number,
  payload: AiHelperRunCreate,
): Promise<AiHelperRunDetail> {
  return api<AiHelperRunDetail>(`/library/tables/${tableId}/ai-helper`, {
    method: "POST",
    body: payload,
  });
}

export function previewAiHelperRun(
  tableId: number,
  payload: AiHelperRunCreate,
): Promise<AiHelperPreview> {
  return api<AiHelperPreview>(`/library/tables/${tableId}/ai-helper/preview`, {
    method: "POST",
    body: payload,
  });
}

export function listAiHelperRuns(
  tableId: number,
): Promise<AiHelperRunListItem[]> {
  return api<AiHelperRunListItem[]>(
    `/library/tables/${tableId}/ai-helper-runs`,
  );
}

export function getAiHelperRun(
  runId: number,
  page = 1,
  pageSize = 50,
): Promise<AiHelperRunDetail> {
  return api<AiHelperRunDetail>(
    `/library/ai-helper-runs/${runId}?page=${page}&page_size=${pageSize}`,
  );
}

export function cancelAiHelperRun(runId: number): Promise<AiHelperRunDetail> {
  return api<AiHelperRunDetail>(`/library/ai-helper-runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function retryFailedAiHelperRun(
  runId: number,
): Promise<AiHelperRunDetail> {
  return api<AiHelperRunDetail>(`/library/ai-helper-runs/${runId}/retry-failed`, {
    method: "POST",
  });
}

export function revertAiHelperRun(runId: number): Promise<AiHelperRunDetail> {
  return api<AiHelperRunDetail>(`/library/ai-helper-runs/${runId}/revert`, {
    method: "POST",
  });
}
