import { api } from "./api";

export type AiHelperMode = "read" | "edit";
export type AiHelperStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

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

export interface AiHelperPreview {
  matched_rows: number;
  provider_code: string | null;
  model: string | null;
  est_cost_usd: number | null;
  est_input_tokens_avg: number | null;
  provider_configured: boolean;
}

export interface AiHelperRunCreate {
  mode: AiHelperMode;
  prompt: string;
  prompt_id?: number | null;
  name?: string | null;
  variable_map: Record<string, number>;
  target_column_id: number;
  provider_code?: string | null;
  model?: string | null;
  max_output_tokens?: number | null;
  input_scope: "full" | "first_pct";
  input_pct?: number | null;
  slice_column_id?: number | null;
  row_ids: number[];
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
