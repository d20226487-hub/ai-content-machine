import { api } from "./api";
import type { CellStatus } from "./types";

// Mirrors backend app/schemas/bulk.py (Normalize section).

/** The selectable transforms. Always applied in this canonical order. */
export type NormalizeOp =
  | "trim"
  | "strip_scheme"
  | "strip_slashes"
  | "lowercase";

export const NORMALIZE_OPERATIONS: NormalizeOp[] = [
  "trim",
  "strip_scheme",
  "strip_slashes",
  "lowercase",
];

export interface HighlightSegment {
  text: string;
  /** Old side: a removed/replaced span. New side: an inserted/replaced span. */
  changed: boolean;
}

export interface NormalizePreviewCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  old_value: string | null;
  new_value: string | null;
  applied_ops: NormalizeOp[];
  old_segments: HighlightSegment[];
  new_segments: HighlightSegment[];
}

export interface NormalizePreview {
  candidates: number;
  would_change: number;
  page: number;
  page_size: number;
  items: NormalizePreviewCell[];
}

export interface NormalizeRunRead {
  id: number;
  table_id: number;
  name: string | null;
  operations: NormalizeOp[];
  column_ids: number[];
  cell_count: number;
  status: "applied" | "reverted";
  created_by_id: number | null;
  created_at: string;
  reverted_at: string | null;
}

export interface NormalizedCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  old_value: string | null;
  new_value: string | null;
  current_value: string | null;
  current_status: CellStatus;
  /** Current value no longer equals what the normalize wrote — reverting
   *  would discard a later edit/regeneration to this cell. */
  drifted: boolean;
  /** Which of the run's transforms actually changed THIS cell. */
  applied_ops: NormalizeOp[];
  /** Before text split for the diff: removed spans struck through. */
  old_segments: HighlightSegment[];
  /** After text split for the diff: inserted spans highlighted. */
  new_segments: HighlightSegment[];
}

export interface NormalizeRunDetail extends NormalizeRunRead {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_cells: number;
  drifted_count: number;
  items: NormalizedCell[];
}

export function previewNormalize(
  tableId: number,
  req: { operations: NormalizeOp[]; column_ids: number[] },
  page = 1,
  pageSize = 25,
): Promise<NormalizePreview> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return api<NormalizePreview>(
    `/library/tables/${tableId}/normalize/preview?${sp.toString()}`,
    { method: "POST", body: req },
  );
}

export function applyNormalize(
  tableId: number,
  req: { operations: NormalizeOp[]; column_ids: number[] },
): Promise<NormalizeRunRead> {
  return api<NormalizeRunRead>(`/library/tables/${tableId}/normalize`, {
    method: "POST",
    body: req,
  });
}

export function listNormalizeRuns(
  tableId: number,
): Promise<NormalizeRunRead[]> {
  return api<NormalizeRunRead[]>(
    `/library/tables/${tableId}/normalize-runs`,
  );
}

export function getNormalizeRun(
  runId: number,
  page = 1,
  pageSize = 25,
  op?: NormalizeOp | "",
): Promise<NormalizeRunDetail> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (op) sp.set("op", op);
  return api<NormalizeRunDetail>(
    `/library/normalize-runs/${runId}?${sp.toString()}`,
  );
}

export function revertNormalizeRun(
  runId: number,
): Promise<NormalizeRunRead> {
  return api<NormalizeRunRead>(`/library/normalize-runs/${runId}/revert`, {
    method: "POST",
  });
}

export function renameNormalizeRun(
  runId: number,
  name: string | null,
): Promise<NormalizeRunRead> {
  return api<NormalizeRunRead>(`/library/normalize-runs/${runId}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteNormalizeRun(runId: number): Promise<void> {
  return api<void>(`/library/normalize-runs/${runId}`, { method: "DELETE" });
}
