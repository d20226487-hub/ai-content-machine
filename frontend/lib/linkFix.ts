import { api } from "./api";
import type { LinkProblem } from "./linkCheck";

// Mirrors backend app/schemas/bulk.py (AI link-fix section).

export type LinkFixStatus =
  | "queued"
  | "running"
  | "cancelled"
  | "done"
  | "failed";

export interface LinkFixRequest {
  source_run_id: number;
  /** Empty/omitted = fix every flagged row; otherwise just these rows. */
  row_ids?: number[] | null;
  /** Mirror the run-page filter bar so only the shown violations are fixed. */
  problem?: LinkProblem | null;
  status_code?: number | null;
  q?: string | null;
  q_negate?: boolean;
  /** Where corrected output goes. Existing column id, OR a new column name to
   *  create one. Both omitted = overwrite the scanned column. */
  target_column_id?: number | null;
  new_column_name?: string | null;
  /** Per-job correction prompt (system override). Empty = Brain default. */
  prompt?: string | null;
}

/** How a correction run rewrote the links: an LLM rewrite ("ai") or a
 *  deterministic swap of each wrong translation link for its expected one
 *  ("replace"). Drives the run's display name. */
export type LinkFixMethod = "ai" | "replace";

export interface LinkFixRun {
  id: number;
  table_id: number;
  name: string | null;
  source_run_id: number | null;
  recheck_run_id: number | null;
  target_column_id: number | null;
  prompt: string | null;
  method: LinkFixMethod;
  status: LinkFixStatus;
  column_ids: number[];
  expected_column_ids: number[];
  total: number;
  done: number;
  failed: number;
  skipped: number;
  reverted_at: string | null;
  error: string | null;
  created_by_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_progress_at: string | null;
}

export interface LinkFixViolationLite {
  problem: LinkProblem;
  link: string;
  detail_code: string | null;
  status_code: number | null;
}

/** One aligned Before/After diff block, shared by both panes so they snippet
 *  in step. `before`/`after` are the per-side text (either may be empty for a
 *  pure insert/delete); `changed` = struck red (Before) / green (After). */
export interface DiffBlock {
  before: string;
  after: string;
  changed: boolean;
}

/** Single-pane diff span for the "Changes" view. */
export interface UnifiedSegment {
  text: string;
  kind: "equal" | "add" | "del";
}

export interface LinkFixCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  state: "pending" | "done" | "failed" | "skipped";
  source_value: string | null;
  old_value: string | null;
  new_value: string | null;
  violations: LinkFixViolationLite[];
  error: string | null;
  diff_blocks: DiffBlock[];
}

/** A cell corrected by an applied fix run — grid tint + Changes view. */
export interface TableFixedCell {
  row_id: number;
  column_id: number;
  segments: UnifiedSegment[];
}

export interface LinkFixRunDetail extends LinkFixRun {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_cells: number;
  items: LinkFixCell[];
}

export function startLinkFix(
  tableId: number,
  req: LinkFixRequest,
): Promise<LinkFixRun> {
  return api<LinkFixRun>(`/library/tables/${tableId}/link-fix`, {
    method: "POST",
    body: req,
  });
}

/** The prompt the fix modal should default to: the previously-used job prompt
 *  for this table, else the global Brain fix-links default. */
export function getLinkFixDefaultPrompt(
  tableId: number,
): Promise<{ prompt: string }> {
  return api<{ prompt: string }>(
    `/library/tables/${tableId}/link-fix/default-prompt`,
  );
}

export function listLinkFixRuns(
  tableId: number,
  opts: { sourceRunId?: number } = {},
): Promise<LinkFixRun[]> {
  const qs =
    opts.sourceRunId != null ? `?source_run_id=${opts.sourceRunId}` : "";
  return api<LinkFixRun[]>(`/library/tables/${tableId}/link-fix-runs${qs}`);
}

export function getLinkFixRun(
  runId: number,
  page = 1,
  pageSize = 25,
): Promise<LinkFixRunDetail> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return api<LinkFixRunDetail>(`/library/link-fix-runs/${runId}?${sp.toString()}`);
}

export function cancelLinkFixRun(runId: number): Promise<LinkFixRun> {
  return api<LinkFixRun>(`/library/link-fix-runs/${runId}/cancel`, {
    method: "POST",
  });
}

export function resumeLinkFixRun(runId: number): Promise<LinkFixRun> {
  return api<LinkFixRun>(`/library/link-fix-runs/${runId}/resume`, {
    method: "POST",
  });
}

export function revertLinkFixRun(runId: number): Promise<LinkFixRun> {
  return api<LinkFixRun>(`/library/link-fix-runs/${runId}/revert`, {
    method: "POST",
  });
}

export function renameLinkFixRun(
  runId: number,
  name: string | null,
): Promise<LinkFixRun> {
  return api<LinkFixRun>(`/library/link-fix-runs/${runId}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteLinkFixRun(runId: number): Promise<void> {
  return api<void>(`/library/link-fix-runs/${runId}`, { method: "DELETE" });
}

/** Cells corrected by an applied fix run, keyed by the target cell they
 *  landed in. Drives the grid green tint + the cell editor "Changes" view. */
export function listTableFixedCells(
  tableId: number,
): Promise<TableFixedCell[]> {
  return api<TableFixedCell[]>(`/library/tables/${tableId}/link-fixes`);
}
