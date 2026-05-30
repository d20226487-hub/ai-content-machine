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
