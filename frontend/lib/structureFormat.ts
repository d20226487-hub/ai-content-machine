import { api } from "./api";
import type { CellStatus } from "./types";

// Mirrors backend app/schemas/bulk.py (Structure & Formatting section).

/** The selectable transforms. Always applied in this canonical order. */
export type StructureFormatOp =
  | "markdown"
  | "response_start"
  | "inline_css"
  | "html_format";

export const SF_OPERATIONS: StructureFormatOp[] = [
  "markdown",
  "response_start",
  "inline_css",
  "html_format",
];

export type StructureFormatStatus =
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "cancelled";

export interface StructureFormatRunRead {
  id: number;
  table_id: number;
  name: string | null;
  operations: StructureFormatOp[];
  column_ids: number[];
  status: StructureFormatStatus;
  total: number;
  done: number;
  failed: number;
  cell_count: number;
  reverted_at: string | null;
  error: string | null;
  created_by_id: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface StructureFormatPreviewCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  applied_ops: StructureFormatOp[];
  change_segments: ChangeSegment[];
}

export interface StructureFormatPreview {
  candidates: number;
  would_change: number;
  page: number;
  page_size: number;
  items: StructureFormatPreviewCell[];
}

/** One span of the condensed single-pane diff. */
export interface ChangeSegment {
  text: string;
  kind: "equal" | "add" | "del";
}

export interface StructureFormatCell {
  row_id: number;
  row_position: number;
  column_id: number;
  column_name: string;
  old_value: string | null;
  new_value: string | null;
  current_value: string | null;
  current_status: CellStatus;
  drifted: boolean;
  /** Which of the run's transforms actually changed THIS cell. */
  applied_ops: StructureFormatOp[];
  /** Condensed old→new diff: del = removed (red), add = added (green). */
  change_segments: ChangeSegment[];
}

export interface StructureFormatRunDetail extends StructureFormatRunRead {
  created_by_name: string | null;
  page: number;
  page_size: number;
  total_cells: number;
  drifted_count: number;
  items: StructureFormatCell[];
}

export function previewStructureFormat(
  tableId: number,
  req: { operations: StructureFormatOp[]; column_ids: number[] },
  page = 1,
  pageSize = 25,
): Promise<StructureFormatPreview> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return api<StructureFormatPreview>(
    `/library/tables/${tableId}/structure-format/preview?${sp.toString()}`,
    { method: "POST", body: req },
  );
}

/** Queues a background run (202) and returns it; poll getStructureFormatRun. */
export function applyStructureFormat(
  tableId: number,
  req: { operations: StructureFormatOp[]; column_ids: number[] },
): Promise<StructureFormatRunRead> {
  return api<StructureFormatRunRead>(
    `/library/tables/${tableId}/structure-format`,
    { method: "POST", body: req },
  );
}

export function listStructureFormatRuns(
  tableId: number,
): Promise<StructureFormatRunRead[]> {
  return api<StructureFormatRunRead[]>(
    `/library/tables/${tableId}/structure-format-runs`,
  );
}

export function getStructureFormatRun(
  runId: number,
  page = 1,
  pageSize = 25,
  op?: StructureFormatOp | "",
): Promise<StructureFormatRunDetail> {
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (op) sp.set("op", op);
  return api<StructureFormatRunDetail>(
    `/library/structure-format-runs/${runId}?${sp.toString()}`,
  );
}

export function revertStructureFormatRun(
  runId: number,
): Promise<StructureFormatRunRead> {
  return api<StructureFormatRunRead>(
    `/library/structure-format-runs/${runId}/revert`,
    { method: "POST" },
  );
}

export function cancelStructureFormatRun(
  runId: number,
): Promise<StructureFormatRunRead> {
  return api<StructureFormatRunRead>(
    `/library/structure-format-runs/${runId}/cancel`,
    { method: "POST" },
  );
}

export function resumeStructureFormatRun(
  runId: number,
): Promise<StructureFormatRunRead> {
  return api<StructureFormatRunRead>(
    `/library/structure-format-runs/${runId}/resume`,
    { method: "POST" },
  );
}

export function renameStructureFormatRun(
  runId: number,
  name: string | null,
): Promise<StructureFormatRunRead> {
  return api<StructureFormatRunRead>(
    `/library/structure-format-runs/${runId}`,
    { method: "PATCH", body: { name } },
  );
}

export function deleteStructureFormatRun(runId: number): Promise<void> {
  return api<void>(`/library/structure-format-runs/${runId}`, {
    method: "DELETE",
  });
}
