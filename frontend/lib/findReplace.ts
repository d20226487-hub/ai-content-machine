import { api } from "./api";
import type { CellStatus } from "./types";

// Mirrors backend app/schemas/bulk.py (find / replace section).

export interface FindReplaceConfig {
  pattern: string;
  replacement: string;
  is_regex: boolean;
  case_sensitive: boolean;
  whole_cell: boolean;
  /** Empty = search every column. */
  column_ids: number[];
}

export interface MatchedCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  value: string;
  status: CellStatus;
  match_count: number;
}

export interface FindResponse {
  total_matches: number;
  total_cells: number;
  page: number;
  page_size: number;
  items: MatchedCell[];
}

export interface FindReplaceRunRead {
  id: number;
  table_id: number;
  name: string | null;
  pattern: string;
  replacement: string;
  is_regex: boolean;
  case_sensitive: boolean;
  whole_cell: boolean;
  column_ids: number[];
  match_count: number;
  cell_count: number;
  status: "applied" | "reverted";
  created_by_id: number | null;
  created_at: string;
  reverted_at: string | null;
}

export interface HighlightSegment {
  text: string;
  /** Old side: the matched span. New side: the inserted replacement. */
  changed: boolean;
}

export interface ReplacedCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  old_value: string | null;
  new_value: string | null;
  current_value: string | null;
  current_status: CellStatus;
  /** Current value no longer equals what the replace wrote — reverting
   *  would discard a later edit/regeneration to this cell. */
  drifted: boolean;
  /** Before text split for the diff: matched spans struck through. */
  old_segments: HighlightSegment[];
  /** After (replaced) text split for the diff: inserted spans highlighted. */
  new_segments: HighlightSegment[];
}

export interface FindReplaceRunDetail extends FindReplaceRunRead {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_cells: number;
  drifted_count: number;
  items: ReplacedCell[];
}

export interface FindReplacePair {
  find: string;
  replace: string;
}

/** Split a multi-line textarea into one value per line, tolerating a single
 *  trailing newline (mirrors the backend `_split_lines`). */
export function splitLines(text: string): string[] {
  const lines = text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Pair a find/replace textarea pair the same way the backend does: an empty
 *  Replace box deletes every Find term, otherwise line N maps to line N. The
 *  returned pairs are for DISPLAY only — the backend re-derives and validates
 *  them, so a UI-visible count mismatch is surfaced via {@link pairMismatch}. */
export function splitPairs(
  pattern: string,
  replacement: string,
): FindReplacePair[] {
  const finds = splitLines(pattern);
  const replaces =
    replacement === "" ? finds.map(() => "") : splitLines(replacement);
  return finds.map((find, i) => ({ find, replace: replaces[i] ?? "" }));
}

/** Find/replace line counts for the live hint. `mismatch` is true when a
 *  Replace was typed but its line count differs from Find (delete-all, i.e.
 *  empty Replace, is never a mismatch). */
export function pairCounts(pattern: string, replacement: string): {
  finds: number;
  replaces: number;
  mismatch: boolean;
} {
  const finds = pattern.trim() === "" ? 0 : splitLines(pattern).length;
  if (replacement === "") return { finds, replaces: 0, mismatch: false };
  const replaces = splitLines(replacement).length;
  return { finds, replaces, mismatch: finds > 0 && replaces !== finds };
}

export function findInTable(
  tableId: number,
  req: FindReplaceConfig & { page?: number; page_size?: number },
): Promise<FindResponse> {
  return api<FindResponse>(`/library/tables/${tableId}/find`, {
    method: "POST",
    body: req,
  });
}

export function replaceInTable(
  tableId: number,
  req: FindReplaceConfig,
): Promise<FindReplaceRunRead> {
  return api<FindReplaceRunRead>(`/library/tables/${tableId}/replace`, {
    method: "POST",
    body: req,
  });
}

export function listReplaceRuns(
  tableId: number,
): Promise<FindReplaceRunRead[]> {
  return api<FindReplaceRunRead[]>(
    `/library/tables/${tableId}/replace-runs`,
  );
}

export function getReplaceRun(
  runId: number,
  page = 1,
  pageSize = 25,
): Promise<FindReplaceRunDetail> {
  return api<FindReplaceRunDetail>(
    `/library/replace-runs/${runId}?page=${page}&page_size=${pageSize}`,
  );
}

export function revertReplaceRun(
  runId: number,
): Promise<FindReplaceRunRead> {
  return api<FindReplaceRunRead>(`/library/replace-runs/${runId}/revert`, {
    method: "POST",
  });
}

export function renameReplaceRun(
  runId: number,
  name: string | null,
): Promise<FindReplaceRunRead> {
  return api<FindReplaceRunRead>(`/library/replace-runs/${runId}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteReplaceRun(runId: number): Promise<void> {
  return api<void>(`/library/replace-runs/${runId}`, { method: "DELETE" });
}
