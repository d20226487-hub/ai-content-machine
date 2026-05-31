"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { ColumnConfigModal } from "@/components/ColumnConfigModal";
import { BulkPublishModal } from "@/components/BulkPublishModal";
import { GenerationProgressBanner } from "@/components/GenerationProgressBanner";
import { GenerationQueueModal } from "@/components/GenerationQueueModal";
import { Modal } from "@/components/Modal";
import { getBrainPrompts } from "@/lib/brain";
import { useT, type TranslationKey } from "@/lib/i18n-context";
import {
  addColumn as apiAddColumn,
  addRow as apiAddRow,
  clearValues,
  deleteColumn as apiDeleteColumn,
  deleteRow as apiDeleteRow,
  enqueueGeneration,
  updateColumn as apiUpdateColumn,
  upsertCells,
} from "@/lib/library";
import type {
  BulkCell,
  BulkColumn,
  BulkRow,
  BulkTable,
  CellStatus,
} from "@/lib/types";

interface Props {
  /** The CURRENT page's data (rows + their cells). Columns are always full. */
  table: BulkTable;
  /** Total rows in the whole table (not just this page). */
  totalRowCount: number;
  /** 0-based current page index (owned by the page component). */
  pageIndex: number;
  pageSize: PageSize;
  /** True while a page fetch is in flight (shows the overlay). */
  loading: boolean;
  onTableChange: (next: BulkTable) => void;
  /** Ask the parent to fetch a different page (always refetches). */
  onPageChange: (index: number) => void;
  onPageSizeChange: (size: PageSize) => void;
  /** Refetch the current page. `silent` skips the loading overlay. */
  reloadPage: (opts?: { silent?: boolean }) => Promise<void>;
  onSavingChange: (saving: boolean, lastSavedAt: number | null) => void;
}

const AUTOSAVE_DEBOUNCE_MS = 600;
const POLL_INTERVAL_MS = 1500;
export const PAGE_SIZE_OPTIONS = [5, 10, 20, 50, 100, 200, 500, 1000] as const;
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 5;
export const PAGE_SIZE_STORAGE_KEY = "acm_bulk_page_size";

const DEFAULT_COL_WIDTH = 200;
const MIN_COL_WIDTH = 80;
const ROW_NUM_WIDTH = 40;
const CHECKBOX_WIDTH = 32;
const ADD_COL_WIDTH = 48;

export function readPageSize(): PageSize {
  if (typeof window === "undefined") return DEFAULT_PAGE_SIZE;
  const v = Number(window.localStorage.getItem(PAGE_SIZE_STORAGE_KEY));
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(v)
    ? (v as PageSize)
    : DEFAULT_PAGE_SIZE;
}

const ROW_HEIGHTS = {
  compact: { labelKey: "bulkGrid.heightCompact" as TranslationKey, px: 28 },
  default: { labelKey: "bulkGrid.heightDefault" as TranslationKey, px: 60 },
  comfortable: { labelKey: "bulkGrid.heightComfortable" as TranslationKey, px: 120 },
  tall: { labelKey: "bulkGrid.heightTall" as TranslationKey, px: 240 },
} as const;
type RowHeightKey = keyof typeof ROW_HEIGHTS;
const ROW_HEIGHT_KEYS = Object.keys(ROW_HEIGHTS) as RowHeightKey[];

function rowHeightKey(tableId: number): string {
  return `acm_bulk_row_height_${tableId}`;
}

function readRowHeight(tableId: number): RowHeightKey {
  if (typeof window === "undefined") return "default";
  const v = window.localStorage.getItem(rowHeightKey(tableId));
  return v && v in ROW_HEIGHTS ? (v as RowHeightKey) : "default";
}

function writeRowHeight(tableId: number, value: RowHeightKey): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(rowHeightKey(tableId), value);
}

function colWidthsKey(tableId: number): string {
  return `acm_bulk_col_widths_${tableId}`;
}

function readColWidths(tableId: number): Record<number, number> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(colWidthsKey(tableId));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeColWidths(tableId: number, widths: Record<number, number>): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(colWidthsKey(tableId), JSON.stringify(widths));
}

export function BulkTableGrid({
  table,
  totalRowCount,
  pageIndex,
  pageSize,
  loading,
  onTableChange,
  onPageChange,
  onPageSizeChange,
  reloadPage,
  onSavingChange,
}: Props) {
  const { t } = useT();
  // Keep cells indexed by "rowId:columnId" for O(1) lookup
  const cellMap = useMemo(() => {
    const m = new Map<string, BulkCell>();
    for (const c of table.cells) m.set(`${c.row_id}:${c.column_id}`, c);
    return m;
  }, [table.cells]);

  // Pending edits live in a ref so flushPending always sees the latest writes,
  // even when invoked from a stale closure (e.g. onBlur fires before React re-renders
  // with the just-typed value). The pendingTick state forces re-renders so cells
  // reflect typing in real time.
  const pendingRef = useRef<Map<string, string | null>>(new Map());
  const [pendingTick, setPendingTick] = useState(0);
  void pendingTick; // read so React knows the render depends on it
  const flushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Serializes flushes: while a flush is in-flight, scheduleFlush re-arms
  // the timer instead of starting a parallel POST. Two overlapping POSTs
  // could return out of order — POST-1 finishing AFTER POST-2 would write
  // the older snapshot into cellMap, briefly wiping the user's newer text
  // from the visible textarea ("auto save deletes my writings"). One in
  // flight at a time eliminates the race entirely.
  // Tracks the in-flight POST as a promise so that `await flushPending()`
  // from drain sites (queue open, publish, unmount, cell-editor save) waits
  // for the running save to settle rather than returning early. A plain
  // boolean would prevent overlap but not allow drain-sites to actually
  // block — they'd open the queue with stale state on the server.
  const inFlightPromiseRef = useRef<Promise<void> | null>(null);
  // Holds the "rowId:colId" key of whichever cell's textarea currently has
  // the cursor. flushPending leaves this key behind in pendingRef instead of
  // saving it, so the server can't echo back a stale value mid-keystroke
  // and wipe what the user is typing. Cleared on blur, where we also fire
  // an immediate flush so the just-left cell saves promptly.
  const focusedCellRef = useRef<string | null>(null);
  // Refs to the latest table + cellMap so flushPending merges into current state
  // even when called from an unmount cleanup or a long-pending timer.
  const tableRef = useRef(table);
  const cellMapRef = useRef(cellMap);
  tableRef.current = table;
  cellMapRef.current = cellMap;
  const onTableChangeRef = useRef(onTableChange);
  onTableChangeRef.current = onTableChange;
  const onSavingChangeRef = useRef(onSavingChange);
  onSavingChangeRef.current = onSavingChange;
  const reloadPageRef = useRef(reloadPage);
  reloadPageRef.current = reloadPage;

  // Modal: viewing a cell's content (HTML viewer)
  const [viewing, setViewing] = useState<{
    column: BulkColumn;
    row: BulkRow;
    cell: BulkCell | null;
  } | null>(null);

  // Configure-column modal
  const [configuring, setConfiguring] = useState<BulkColumn | null>(null);

  // Selected row IDs for batch generation (persists across pages)
  const [selectedRowIds, setSelectedRowIds] = useState<Set<number>>(new Set());

  // Modal: cell error details
  const [errorView, setErrorView] = useState<{ cell: BulkCell; column: BulkColumn } | null>(null);

  // Inline column rename (double-click the header name to start)
  const [renamingColumnId, setRenamingColumnId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  // Brain default target language for the Translate panel. Loaded once
  // per mount; falls back to 'ru' so the modal stays usable when the
  // admin hasn't visited Settings → Brain yet.
  const [translateDefaultLang, setTranslateDefaultLang] = useState<string>("ru");
  useEffect(() => {
    let ignored = false;
    getBrainPrompts()
      .then((b) => {
        if (!ignored) {
          setTranslateDefaultLang(
            (b.translate.default_target_language || "ru").toLowerCase(),
          );
        }
      })
      .catch(() => {
        /* keep the 'ru' fallback — non-fatal */
      });
    return () => {
      ignored = true;
    };
  }, []);

  async function commitColumnRename(col: BulkColumn) {
    const next = renameDraft.trim();
    setRenamingColumnId(null);
    if (!next || next === col.name) return;
    try {
      const updated = await apiUpdateColumn(table.id, col.id, { name: next });
      onTableChange({
        ...table,
        columns: table.columns.map((c) => (c.id === col.id ? updated : c)),
      });
    } catch (err) {
      console.error("[Bulk] inline rename failed", err);
    }
  }

  // Pagination is owned by the page component (server-side paging). When the
  // user wants to switch pages we flush any pending edits first so nothing
  // typed on the outgoing page is lost.
  const [allRowsSelected, setAllRowsSelected] = useState(false);

  async function goToPage(index: number): Promise<void> {
    await flushPending();
    onPageChange(index);
  }

  async function changePageSize(size: PageSize): Promise<void> {
    await flushPending();
    onPageSizeChange(size);
  }

  // ---- Column widths (per-table, persisted in localStorage) ----
  const [colWidths, setColWidths] = useState<Record<number, number>>({});
  useEffect(() => {
    setColWidths(readColWidths(table.id));
  }, [table.id]);

  // ---- Row height (per-table, persisted in localStorage) ----
  const [rowHeight, setRowHeight] = useState<RowHeightKey>("default");
  useEffect(() => {
    setRowHeight(readRowHeight(table.id));
  }, [table.id]);
  function changeRowHeight(value: RowHeightKey): void {
    setRowHeight(value);
    writeRowHeight(table.id, value);
  }
  const rowHeightPx = ROW_HEIGHTS[rowHeight].px;

  // Holds the cleanup callback for an in-flight column resize, so we can run
  // it from the component's unmount path. Without this, unmounting mid-drag
  // (e.g. user navigates away while holding the mouse down) leaks the
  // global mousemove/mouseup listeners on document.
  const resizeCleanupRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    return () => {
      resizeCleanupRef.current?.();
      resizeCleanupRef.current = null;
    };
  }, []);

  function startResize(colId: number, e: React.MouseEvent): void {
    e.preventDefault();
    // If a previous drag is somehow still pending, tear it down first.
    resizeCleanupRef.current?.();

    const startX = e.clientX;
    const startW = colWidths[colId] ?? DEFAULT_COL_WIDTH;
    // Disable text selection during the drag
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    function onMove(ev: MouseEvent): void {
      const next = Math.max(MIN_COL_WIDTH, startW + (ev.clientX - startX));
      setColWidths((prev) => ({ ...prev, [colId]: next }));
    }
    function cleanup(): void {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      resizeCleanupRef.current = null;
    }
    function onUp(): void {
      cleanup();
      // Persist final widths
      setColWidths((prev) => {
        writeColWidths(table.id, prev);
        return prev;
      });
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    resizeCleanupRef.current = cleanup;
  }

  // Rows for the current page come straight from the server — no client
  // slicing. `pageStart` is still derived so the row "#" numbers and the
  // "Showing X–Y of Z" footer reflect absolute positions.
  const totalRows = totalRowCount;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const safePageIndex = Math.min(pageIndex, totalPages - 1);
  const pageStart = safePageIndex * pageSize;
  const pageEnd = pageStart + pageSize;
  const visibleRows = table.rows;

  // ---- Polling: while ANY cell is 'generating', re-fetch the whole table.
  const generatingCount = useMemo(
    () => Array.from(cellMap.values()).filter((c) => c.status === "generating").length,
    [cellMap],
  );

  useEffect(() => {
    if (generatingCount === 0) return;
    let cancelled = false;
    const tick = async () => {
      try {
        // Silently refetch the current page so 'generating' cells flip to
        // their final status without flashing the loading overlay.
        if (!cancelled) await reloadPageRef.current({ silent: true });
      } catch (err) {
        console.error("[Bulk] poll failed", err);
      }
    };
    const handle = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [generatingCount]);

  function getCellValue(rowId: number, colId: number): string {
    const k = `${rowId}:${colId}`;
    if (pendingRef.current.has(k)) return pendingRef.current.get(k) ?? "";
    return cellMap.get(k)?.value ?? "";
  }

  function getCellStatus(rowId: number, colId: number): CellStatus {
    const k = `${rowId}:${colId}`;
    if (pendingRef.current.has(k)) {
      return pendingRef.current.get(k) ? "manual" : "empty";
    }
    return cellMap.get(k)?.status ?? "empty";
  }

  function scheduleFlush() {
    if (flushTimer.current) clearTimeout(flushTimer.current);
    flushTimer.current = setTimeout(() => void flushPending(), AUTOSAVE_DEBOUNCE_MS);
  }

  async function flushPending(): Promise<void> {
    flushTimer.current = null;
    // Wait for any in-flight save to settle before starting our own. This
    // serializes POSTs (so they can't return out of order and clobber
    // cellMap) AND makes `await flushPending()` from drain sites actually
    // wait for the running save instead of returning instantly.
    while (inFlightPromiseRef.current) {
      try {
        await inFlightPromiseRef.current;
      } catch {
        /* the in-flight branch handles its own errors */
      }
    }

    // Skip the currently-focused cell's pending write. Saving it while the
    // user is still typing risks the server echoing a stale value back into
    // cellMap and wiping the textarea. Its entry stays in pendingRef and
    // gets flushed on blur (or unmount, which clears the focus marker).
    const focusedKey = focusedCellRef.current;
    const snapshot = new Map<string, string | null>();
    for (const [k, v] of pendingRef.current) {
      if (k === focusedKey) continue;
      snapshot.set(k, v);
    }
    if (snapshot.size === 0) return;
    // Move the to-be-flushed entries out of pendingRef. The focused entry
    // (if any) stays so the user's in-progress text survives.
    const nextPending = new Map<string, string | null>();
    if (focusedKey && pendingRef.current.has(focusedKey)) {
      nextPending.set(focusedKey, pendingRef.current.get(focusedKey)!);
    }
    pendingRef.current = nextPending;

    const writes = Array.from(snapshot.entries()).map(([key, value]) => {
      const [rowIdStr, colIdStr] = key.split(":");
      return {
        row_id: Number(rowIdStr),
        column_id: Number(colIdStr),
        value: value ?? null,
      };
    });

    const promise = (async () => {
      onSavingChangeRef.current(true, null);
      try {
        const written = await upsertCells(tableRef.current.id, writes);
        const newCellMap = new Map(cellMapRef.current);
        for (const w of written) {
          const key = `${w.row_id}:${w.column_id}`;
          // Skip cells where the user has typed something new since we
          // snapshotted. Writing the server's (now-stale) value here would
          // briefly clobber the textarea on the next render — the typing
          // in pendingRef is the truth and will flush on the next tick.
          if (pendingRef.current.has(key)) continue;
          const existing = newCellMap.get(key);
          newCellMap.set(key, {
            id: w.id,
            row_id: w.row_id,
            column_id: w.column_id,
            value: w.value,
            status: w.status as CellStatus,
            error: existing?.error ?? null,
            model_used: existing?.model_used ?? null,
            generated_at: existing?.generated_at ?? null,
            updated_at: w.updated_at,
          });
        }
        onTableChangeRef.current({
          ...tableRef.current,
          cells: Array.from(newCellMap.values()),
        });
        onSavingChangeRef.current(false, Date.now());
      } catch (err) {
        console.error("[Bulk] cell save failed", err);
        // Restore the unsaved writes (don't clobber anything the user has typed since).
        for (const [k, v] of snapshot.entries()) {
          if (!pendingRef.current.has(k)) pendingRef.current.set(k, v);
        }
        setPendingTick((n) => n + 1);
        onSavingChangeRef.current(false, null);
      }
    })();
    inFlightPromiseRef.current = promise;
    try {
      await promise;
    } finally {
      if (inFlightPromiseRef.current === promise) {
        inFlightPromiseRef.current = null;
      }
    }

    // If non-focused pending writes accumulated during the await, kick off
    // another flush so they get saved on the autosave cadence.
    const stillPending = Array.from(pendingRef.current.keys()).filter(
      (k) => k !== focusedCellRef.current,
    );
    if (stillPending.length > 0) scheduleFlush();
  }

  // Flush on unmount. Clear the focus marker first so the unmount drain
  // includes whatever the user was typing at the moment of teardown —
  // otherwise flushPending would skip the focused cell and lose it.
  useEffect(() => {
    return () => {
      if (flushTimer.current) {
        clearTimeout(flushTimer.current);
      }
      focusedCellRef.current = null;
      void flushPending();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setCell(rowId: number, colId: number, value: string) {
    const key = `${rowId}:${colId}`;
    pendingRef.current.set(key, value === "" ? null : value);
    setPendingTick((n) => n + 1);
    scheduleFlush();
  }

  // ---- Generation queue ----
  const [queueOpen, setQueueOpen] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);

  async function openQueue(): Promise<void> {
    // Flush any pending cell edits first so what's in the queue reflects reality.
    await flushPending();
    setQueueOpen(true);
  }

  // ---- Clear values for selected rows ----
  // Server-side now: a selection can span pages (select-all-N), so the
  // browser no longer holds every cell to build the write batch. The
  // clear-values endpoint wipes them in one UPDATE.
  async function clearSelectedRowValues(): Promise<void> {
    const count = allRowsSelected ? totalRows : selectedRowIds.size;
    if (count === 0) return;
    if (!window.confirm(t("bulkGrid.confirmClearValues", { count }))) return;
    // Cancel any pending typing on the affected rows so they don't re-save.
    for (const key of Array.from(pendingRef.current.keys())) {
      const [r] = key.split(":");
      if (allRowsSelected || selectedRowIds.has(Number(r))) {
        pendingRef.current.delete(key);
      }
    }
    onSavingChangeRef.current(true, null);
    try {
      await clearValues(
        table.id,
        allRowsSelected
          ? { all: true }
          : { row_ids: Array.from(selectedRowIds) },
      );
      await reloadPage();
      onSavingChangeRef.current(false, Date.now());
    } catch (err) {
      console.error("[Bulk] clear values failed", err);
      alert(t("bulkGrid.clearValuesFailed"));
      onSavingChangeRef.current(false, null);
    }
  }

  async function onQueueEnqueued(_message: string): Promise<void> {
    // Re-fetch the current page to flip cells to 'generating'; polling will
    // take it from there.
    try {
      await reloadPage({ silent: true });
    } catch (err) {
      console.error("[Bulk] post-enqueue refresh failed", err);
    }
  }

  function selectionToggle(rowId: number) {
    // An explicit per-row toggle exits "all rows" mode — from here the
    // selection is whatever IDs are actually enumerated.
    setAllRowsSelected(false);
    setSelectedRowIds((cur) => {
      const next = new Set(cur);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  function selectionAllOnPage() {
    setSelectedRowIds((cur) => {
      const next = new Set(cur);
      for (const r of visibleRows) next.add(r.id);
      return next;
    });
  }

  function selectionClearPage() {
    setAllRowsSelected(false);
    setSelectedRowIds((cur) => {
      const next = new Set(cur);
      for (const r of visibleRows) next.delete(r.id);
      return next;
    });
  }

  // "Select all N" can't enumerate row IDs across pages (we only hold the
  // current page), so it sets a flag the cross-page operations honor as
  // "every row". The current page's IDs are still tracked so the checkboxes
  // render checked.
  function selectionAllInTable() {
    setAllRowsSelected(true);
    setSelectedRowIds(new Set(visibleRows.map((r) => r.id)));
  }

  function selectionClear() {
    setAllRowsSelected(false);
    setSelectedRowIds(new Set());
  }

  // Effective selected count: total when "all rows" is on, else the
  // enumerated set. Drives the toolbar labels + footer.
  const selectedCount = allRowsSelected ? totalRows : selectedRowIds.size;

  const allOnPageSelected =
    visibleRows.length > 0 &&
    (allRowsSelected || visibleRows.every((r) => selectedRowIds.has(r.id)));

  const outputColsWithPrompt = table.columns.filter(
    (c) => c.kind === "output" && c.prompt_id != null,
  );

  // ---- Column actions ----

  async function onAddColumnClick() {
    const name = window.prompt(t("bulkGrid.addColumnPrompt"));
    if (!name?.trim()) return;
    try {
      const col = await apiAddColumn(table.id, { name: name.trim(), kind: "input" });
      onTableChange({ ...table, columns: [...table.columns, col] });
    } catch (err) {
      console.error("[Bulk] add column failed", err);
      alert(t("bulkGrid.addColumnFailed"));
    }
  }

  async function onDeleteColumn(col: BulkColumn) {
    if (!window.confirm(t("bulkGrid.confirmDeleteColumn", { name: col.name }))) return;
    try {
      await apiDeleteColumn(table.id, col.id);
      onTableChange({
        ...table,
        columns: table.columns.filter((c) => c.id !== col.id),
        cells: table.cells.filter((c) => c.column_id !== col.id),
      });
    } catch (err) {
      console.error("[Bulk] delete column failed", err);
    }
  }

  async function onToggleKind(col: BulkColumn) {
    const newKind = col.kind === "input" ? "output" : "input";
    try {
      const updated = await apiUpdateColumn(table.id, col.id, { kind: newKind });
      onTableChange({
        ...table,
        columns: table.columns.map((c) => (c.id === col.id ? updated : c)),
      });
    } catch (err) {
      console.error("[Bulk] toggle kind failed", err);
    }
  }

  // ---- Row actions ----

  async function onAddRow() {
    try {
      await apiAddRow(table.id);
      // The new row is appended at the end. Its ordinal index == old total,
      // so its page is floor(total / pageSize). Navigating there refetches
      // and shows it (and refreshes total_row_count).
      const newPage = Math.floor(totalRows / pageSize);
      await flushPending();
      onPageChange(newPage);
    } catch (err) {
      console.error("[Bulk] add row failed", err);
    }
  }

  async function onDeleteRow(row: BulkRow) {
    if (!window.confirm(t("bulkGrid.confirmDeleteRow"))) return;
    try {
      await apiDeleteRow(table.id, row.id);
      // Refetch the page — total shrank and later rows shift up a slot.
      await reloadPage();
    } catch (err) {
      console.error("[Bulk] delete row failed", err);
    }
  }

  function openCell(row: BulkRow, col: BulkColumn) {
    const cell = cellMap.get(`${row.id}:${col.id}`) ?? null;
    setViewing({ row, column: col, cell });
  }

  // Refresh the current page when a generation run finishes so the cell
  // statuses ('generated' / 'failed') paint in without a manual reload.
  // Re-fetches the page rather than mutating state in place — the workers
  // update cells server-side and the local pendingRef / autosave state has
  // nothing to merge.
  const refreshOnRunFinish = useCallback(async () => {
    try {
      await reloadPageRef.current({ silent: true });
    } catch {
      // Best-effort; if the refresh fails the next manual interaction
      // will catch up.
    }
  }, []);

  return (
    <>
      {/* Progress banner for an in-flight bulk-generation run. Hides
          itself when no run is active for the table. */}
      <GenerationProgressBanner
        tableId={table.id}
        onRunFinished={refreshOnRunFinish}
      />

      {/* Generation toolbar */}
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-900">
        <span className="text-neutral-500 dark:text-neutral-400">
          {selectedCount > 0
            ? t("bulkGrid.toolbarSelected", { count: selectedCount })
            : t("bulkGrid.toolbarClickGenerate")}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {selectedCount > 0 && (
            <>
              <button
                type="button"
                onClick={() => void clearSelectedRowValues()}
                className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-red-600 hover:bg-red-50 dark:border-neutral-700 dark:text-red-400 dark:hover:bg-red-950/40"
                title={t("bulkGrid.clearValuesHint")}
              >
                {t("bulkGrid.clearValues")}
              </button>
              <button
                type="button"
                onClick={selectionClear}
                className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                {t("bulkGrid.clearSelection")}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setPublishOpen(true)}
            className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            title={t("bulkGrid.publishHint")}
          >
            {selectedCount > 0
              ? t("bulkGrid.publishLabelSelected", { count: selectedCount })
              : t("bulkGrid.publishLabel")}
          </button>
          <button
            type="button"
            onClick={() => void openQueue()}
            disabled={outputColsWithPrompt.length === 0}
            className="rounded-md bg-neutral-900 px-3 py-1 font-medium text-white hover:bg-neutral-800 disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            title={
              outputColsWithPrompt.length === 0
                ? t("bulkGrid.generateDisabledHint")
                : t("bulkGrid.generateOpenHint")
            }
          >
            {selectedCount > 0
              ? t("bulkGrid.generateLabelSelected", { count: selectedCount })
              : t("bulkGrid.generateLabel")}
          </button>
        </div>
      </div>

      <div className="relative overflow-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        {loading && (
          <div className="pointer-events-none absolute inset-0 z-30 flex items-start justify-center bg-white/50 pt-10 dark:bg-neutral-900/50">
            <span className="rounded-md bg-neutral-900/80 px-3 py-1 text-xs font-medium text-white dark:bg-neutral-100/80 dark:text-neutral-900">
              {t("common.loading")}
            </span>
          </div>
        )}
        <table
          className="border-separate border-spacing-0 text-sm"
          style={{ tableLayout: "fixed" }}
        >
          <colgroup>
            <col style={{ width: CHECKBOX_WIDTH }} />
            <col style={{ width: ROW_NUM_WIDTH }} />
            {table.columns.map((col) => (
              <col
                key={col.id}
                style={{ width: colWidths[col.id] ?? DEFAULT_COL_WIDTH }}
              />
            ))}
            <col style={{ width: ADD_COL_WIDTH }} />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-neutral-50 dark:bg-neutral-950">
            <tr>
              <th className="w-8 border-b border-neutral-200 px-1 py-2 text-center dark:border-neutral-800">
                <input
                  type="checkbox"
                  checked={allOnPageSelected}
                  onChange={(e) =>
                    e.target.checked ? selectionAllOnPage() : selectionClearPage()
                  }
                  className="h-3.5 w-3.5"
                  title={t("bulkGrid.selectAllOnPage")}
                />
              </th>
              <th className="w-10 border-b border-neutral-200 px-2 py-2 text-center text-[10px] font-medium uppercase tracking-wide text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                #
              </th>
              {table.columns.map((col) => (
                <th
                  key={col.id}
                  className="group relative border-b border-l border-neutral-200 px-2 py-2 text-left dark:border-neutral-800"
                >
                  {/* Drag handle pinned to the right edge of the cell */}
                  <div
                    onMouseDown={(e) => startResize(col.id, e)}
                    onDoubleClick={(e) => {
                      // Double-click handle resets that column to default width.
                      e.stopPropagation();
                      setColWidths((prev) => {
                        const next = { ...prev };
                        delete next[col.id];
                        writeColWidths(table.id, next);
                        return next;
                      });
                    }}
                    title={t("bulkGrid.dragResizeHint")}
                    className="absolute right-0 top-0 z-20 h-full w-1.5 cursor-col-resize bg-transparent hover:bg-blue-400/60 active:bg-blue-500/80"
                  />
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      {renamingColumnId === col.id ? (
                        <input
                          autoFocus
                          type="text"
                          value={renameDraft}
                          onChange={(e) => setRenameDraft(e.target.value)}
                          onBlur={() => void commitColumnRename(col)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void commitColumnRename(col);
                            if (e.key === "Escape") setRenamingColumnId(null);
                          }}
                          className="block w-full rounded border border-neutral-300 px-1 py-0.5 text-xs font-medium text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                        />
                      ) : (
                        <p
                          onDoubleClick={() => {
                            setRenamingColumnId(col.id);
                            setRenameDraft(col.name);
                          }}
                          title={t("bulkGrid.doubleClickRename")}
                          className="truncate cursor-text text-xs font-medium text-neutral-900 dark:text-neutral-100"
                        >
                          {col.name}
                        </p>
                      )}
                      <p className="text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                        {col.kind === "output" ? t("bulkGrid.colKindOutput") : t("bulkGrid.colKindInput")}
                        {col.kind === "output" && col.prompt_id == null && t("bulkGrid.colNoPrompt")}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-0.5 text-[11px] text-neutral-500 opacity-0 transition-opacity group-hover:opacity-100 dark:text-neutral-400">
                      {col.kind === "output" && (
                        <button
                          onClick={() => setConfiguring(col)}
                          className="rounded px-1 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                          title={t("bulkGrid.cfgPromptHint")}
                        >
                          ⚙
                        </button>
                      )}
                      <button
                        onClick={() => onToggleKind(col)}
                        className="rounded px-1 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                        title={t("bulkGrid.toggleKindHint", {
                          kind: col.kind === "input" ? t("bulkGrid.colKindOutput") : t("bulkGrid.colKindInput"),
                        })}
                      >
                        ⇄
                      </button>
                      <button
                        onClick={() => onDeleteColumn(col)}
                        className="rounded px-1 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
                        title={t("bulkGrid.deleteColumnHint")}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                </th>
              ))}
              <th className="w-12 border-b border-l border-neutral-200 px-2 py-2 text-center dark:border-neutral-800">
                <button
                  onClick={onAddColumnClick}
                  title={t("bulkGrid.addColumnHint")}
                  className="text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
                >
                  +
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, relIdx) => {
              const absoluteIdx = pageStart + relIdx;
              return (
              <tr key={row.id} className="group">
                <td className="border-b border-neutral-200 px-1 py-1 text-center dark:border-neutral-800">
                  <input
                    type="checkbox"
                    checked={selectedRowIds.has(row.id)}
                    onChange={() => selectionToggle(row.id)}
                    className="h-3.5 w-3.5"
                  />
                </td>
                <td className="border-b border-neutral-200 px-2 py-1 text-center text-[10px] text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                  <span className="group-hover:hidden">{absoluteIdx + 1}</span>
                  <button
                    onClick={() => onDeleteRow(row)}
                    title={t("bulkGrid.deleteRowHint")}
                    className="hidden hover:text-red-600 group-hover:inline dark:hover:text-red-400"
                  >
                    ×
                  </button>
                </td>
                {table.columns.map((col) => {
                  const cellRef = cellMap.get(`${row.id}:${col.id}`) ?? null;
                  const value = getCellValue(row.id, col.id);
                  const status = getCellStatus(row.id, col.id);
                  return (
                    <td
                      key={col.id}
                      onDoubleClick={() => {
                        if (status === "generating" || status === "failed") return;
                        openCell(row, col);
                      }}
                      title={t("bulkGrid.openViewerHint")}
                      className={
                        "group/cell relative border-b border-l border-neutral-200 align-top dark:border-neutral-800 " +
                        (status === "generating"
                          ? "bg-amber-50 dark:bg-amber-950/30"
                          : status === "failed"
                            ? "bg-red-50 dark:bg-red-950/30"
                            : status === "generated"
                              ? "bg-green-50/30 dark:bg-green-950/20"
                              : "")
                      }
                    >
                      {status === "generating" ? (
                        <div
                          style={{ height: rowHeightPx }}
                          className="flex items-center px-2 text-xs text-amber-700 dark:text-amber-300"
                        >
                          <span className="mr-2 inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />
                          {t("bulkGrid.generating")}
                        </div>
                      ) : status === "failed" ? (
                        <button
                          type="button"
                          onClick={() => {
                            if (cellRef) setErrorView({ cell: cellRef, column: col });
                          }}
                          style={{ height: rowHeightPx }}
                          className="flex w-full items-center px-2 text-left text-xs text-red-700 hover:underline dark:text-red-300"
                          title={t("bulkGrid.failedHint")}
                        >
                          {t("bulkGrid.failedClickToSee")}
                        </button>
                      ) : (
                        <>
                          <textarea
                            value={value}
                            onChange={(e) => setCell(row.id, col.id, e.target.value)}
                            onFocus={() => {
                              focusedCellRef.current = `${row.id}:${col.id}`;
                            }}
                            onBlur={() => {
                              focusedCellRef.current = null;
                              void flushPending();
                            }}
                            placeholder={col.kind === "output" ? t("bulkGrid.outputPlaceholder") : ""}
                            style={{ height: rowHeightPx }}
                            className="block w-full resize-none border-0 bg-transparent px-2 py-1 pr-6 text-xs text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:text-neutral-100 [&::-webkit-scrollbar]:hidden [scrollbar-width:none]"
                          />
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openCell(row, col);
                            }}
                            title={t("bulkGrid.openViewer")}
                            tabIndex={-1}
                            className="absolute right-1 top-1 z-10 rounded px-1 text-[10px] text-neutral-400 opacity-0 hover:bg-neutral-100 hover:text-neutral-900 group-hover/cell:opacity-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                          >
                            ↗
                          </button>
                        </>
                      )}
                    </td>
                  );
                })}
                <td className="border-b border-l border-neutral-200 dark:border-neutral-800" />
              </tr>
            );
            })}
            <tr>
              <td colSpan={table.columns.length + 3} className="px-2 py-2">
                <button
                  onClick={onAddRow}
                  className="text-xs font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
                >
                  {t("bulkGrid.addRow")}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-neutral-200 bg-white px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-900">
        <div className="flex items-center gap-2 text-neutral-600 dark:text-neutral-400">
          <span>
            {totalRows === 0
              ? t("bulkGrid.noRows")
              : t("bulkGrid.rowsRange", {
                  from: pageStart + 1,
                  to: Math.min(pageEnd, totalRows),
                  total: totalRows,
                })}
          </span>
          {selectedCount > 0 && (
            <>
              <span aria-hidden>·</span>
              <span>{t("bulkGrid.selectedSuffix", { count: selectedCount })}</span>
              {!allRowsSelected && selectedCount < totalRows && (
                <button
                  type="button"
                  onClick={selectionAllInTable}
                  className="ml-1 underline hover:text-neutral-900 dark:hover:text-neutral-100"
                >
                  {t("bulkGrid.selectAllN", { total: totalRows })}
                </button>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2">
            <span className="text-neutral-500 dark:text-neutral-400">{t("bulkGrid.rowHeight")}</span>
            <select
              value={rowHeight}
              onChange={(e) => changeRowHeight(e.target.value as RowHeightKey)}
              className="rounded-md border border-neutral-300 px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              {ROW_HEIGHT_KEYS.map((k) => (
                <option key={k} value={k}>
                  {t(ROW_HEIGHTS[k].labelKey)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2">
            <span className="text-neutral-500 dark:text-neutral-400">{t("bulkGrid.rowsPerPage")}</span>
            <select
              value={pageSize}
              onChange={(e) => void changePageSize(Number(e.target.value) as PageSize)}
              className="rounded-md border border-neutral-300 px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void goToPage(0)}
              disabled={safePageIndex === 0 || loading}
              className="rounded border border-neutral-300 px-2 py-0.5 disabled:opacity-30 dark:border-neutral-700"
              title={t("bulkGrid.firstPage")}
            >
              «
            </button>
            <button
              type="button"
              onClick={() => void goToPage(Math.max(0, safePageIndex - 1))}
              disabled={safePageIndex === 0 || loading}
              className="rounded border border-neutral-300 px-2 py-0.5 disabled:opacity-30 dark:border-neutral-700"
              title={t("bulkGrid.previousPage")}
            >
              ‹
            </button>
            <span className="px-2 text-neutral-700 dark:text-neutral-300">
              {t("common.pageXofY", { page: safePageIndex + 1, total: totalPages })}
            </span>
            <button
              type="button"
              onClick={() => void goToPage(Math.min(totalPages - 1, safePageIndex + 1))}
              disabled={safePageIndex >= totalPages - 1 || loading}
              className="rounded border border-neutral-300 px-2 py-0.5 disabled:opacity-30 dark:border-neutral-700"
              title={t("bulkGrid.nextPage")}
            >
              ›
            </button>
            <button
              type="button"
              onClick={() => void goToPage(totalPages - 1)}
              disabled={safePageIndex >= totalPages - 1 || loading}
              className="rounded border border-neutral-300 px-2 py-0.5 disabled:opacity-30 dark:border-neutral-700"
              title={t("bulkGrid.lastPage")}
            >
              »
            </button>
          </div>
        </div>
      </div>

      {viewing && (
        <CellEditorModal
          title={`${viewing.column.name} · ${t("colCfg.rowHash", {
            // Absolute row number = page offset + position within this page.
            n: pageStart + table.rows.findIndex((r) => r.id === viewing.row.id) + 1,
          })}`}
          initialValue={getCellValue(viewing.row.id, viewing.column.id)}
          // Output columns land in preview by default — the user
          // usually wants to read the generated HTML first and only
          // flip to edit if they want to tweak. Input columns stay
          // on edit (their content is what the user types in, no
          // rendered preview makes sense).
          defaultMode={viewing.column.kind === "output" ? "preview" : "edit"}
          // Translation panel only makes sense for output cells that
          // already have a saved value to translate.
          translation={
            viewing.column.kind === "output" &&
            viewing.cell &&
            viewing.cell.value &&
            viewing.cell.value.trim().length > 0
              ? {
                  tableId: table.id,
                  rowId: viewing.row.id,
                  columnId: viewing.column.id,
                  initial: viewing.cell.translations ?? null,
                  defaultTargetLanguage: translateDefaultLang,
                  onTranslated: (lang, entry) => {
                    const rowId = viewing.row.id;
                    const colId = viewing.column.id;
                    onTableChange({
                      ...table,
                      cells: table.cells.map((c) =>
                        c.row_id === rowId && c.column_id === colId
                          ? {
                              ...c,
                              translations: {
                                ...(c.translations ?? {}),
                                [lang]: entry,
                              },
                            }
                          : c,
                      ),
                    });
                  },
                }
              : undefined
          }
          onClose={() => setViewing(null)}
          onSave={async (next) => {
            // Push directly through the same upsert path the inline
            // textarea uses, so status flips to 'manual' and the table
            // state stays in sync.
            const rowId = viewing.row.id;
            const colId = viewing.column.id;
            // Clear focusedCellRef first. The autosave path deliberately
            // SKIPS the focused cell so a quick blur+autosave doesn't
            // clobber in-progress typing — but on an explicit modal
            // Save, that heuristic backfires: if the inline textarea
            // for this same cell still holds focus (browser timing
            // varies on click→blur ordering when opening the modal),
            // flushPending would skip our write, the snapshot becomes
            // empty, the function returns immediately, and the user
            // experiences a no-op save where the button feels stuck
            // until something else triggers a real flush.
            focusedCellRef.current = null;
            pendingRef.current.set(`${rowId}:${colId}`, next === "" ? null : next);
            await flushPending();
            setViewing(null);
          }}
        />
      )}

      {configuring && (
        <ColumnConfigModal
          table={table}
          column={configuring}
          onClose={() => setConfiguring(null)}
          onSaved={(col) =>
            onTableChange({
              ...table,
              columns: table.columns.map((c) => (c.id === col.id ? col : c)),
            })
          }
        />
      )}

      {publishOpen && (
        <BulkPublishModal
          table={table}
          totalRowCount={totalRows}
          allRowsSelected={allRowsSelected}
          selectedRowIds={Array.from(selectedRowIds)}
          onClose={() => setPublishOpen(false)}
        />
      )}

      {queueOpen && (
        <GenerationQueueModal
          table={table}
          totalRowCount={totalRows}
          allRowsSelected={allRowsSelected}
          preselectedRowIds={Array.from(selectedRowIds)}
          onClose={() => setQueueOpen(false)}
          onEnqueued={(msg) => void onQueueEnqueued(msg)}
        />
      )}

      {errorView && (
        <Modal onClose={() => setErrorView(null)} size="max-w-2xl">
          <h3 className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {t("bulkGrid.errorTitle", { col: errorView.column.name })}
          </h3>
          <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md bg-red-50 p-3 font-mono text-xs text-red-900 dark:bg-red-950/50 dark:text-red-200">
            {errorView.cell.error ?? t("bulkGrid.errorEmpty")}
          </pre>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={async () => {
                if (!errorView.cell) return;
                const cell = errorView.cell;
                setErrorView(null);
                try {
                  await enqueueGeneration(table.id, {
                    row_ids: [cell.row_id],
                    column_ids: [cell.column_id],
                    mode: "all",
                  });
                  await reloadPage({ silent: true });
                } catch (err) {
                  console.error("[Bulk] retry cell failed", err);
                  alert(t("bulkGrid.retryFailed"));
                }
              }}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {t("bulkGrid.retryCell")}
            </button>
            <button
              onClick={() => setErrorView(null)}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              {t("common.close")}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
