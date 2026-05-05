"use client";

import { useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import {
  enqueueGeneration,
  type GenerateMode,
  type GenerateRequestPayload,
} from "@/lib/library";
import type { BulkCell, BulkTable } from "@/lib/types";

interface Props {
  table: BulkTable;
  preselectedRowIds: number[];
  onClose: () => void;
  onEnqueued: (message: string) => void;
}

type RowMode = "all" | "range" | "selected";

export function GenerationQueueModal({
  table,
  preselectedRowIds,
  onClose,
  onEnqueued,
}: Props) {
  const { t } = useT();
  const outputCols = useMemo(
    () => table.columns.filter((c) => c.kind === "output"),
    [table.columns],
  );
  const runnableColumnIds = useMemo(
    () => outputCols.filter((c) => c.prompt_id != null).map((c) => c.id),
    [outputCols],
  );
  const [pickedColumnIds, setPickedColumnIds] = useState<Set<number>>(
    new Set(runnableColumnIds),
  );

  function toggleColumn(id: number) {
    setPickedColumnIds((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const [rowMode, setRowMode] = useState<RowMode>(
    preselectedRowIds.length > 0 ? "selected" : "all",
  );
  const [rangeStart, setRangeStart] = useState(1);
  const [rangeEnd, setRangeEnd] = useState(table.rows.length);

  const targetRowIds = useMemo<number[]>(() => {
    if (table.rows.length === 0) return [];
    if (rowMode === "all") return table.rows.map((r) => r.id);
    if (rowMode === "selected") return preselectedRowIds;
    const a = Math.max(1, Math.min(rangeStart, table.rows.length));
    const b = Math.max(a, Math.min(rangeEnd, table.rows.length));
    return table.rows.slice(a - 1, b).map((r) => r.id);
  }, [rowMode, rangeStart, rangeEnd, table.rows, preselectedRowIds]);

  const [mode, setMode] = useState<GenerateMode>("empty");

  const cellMap = useMemo(() => {
    const m = new Map<string, BulkCell>();
    for (const c of table.cells) m.set(`${c.row_id}:${c.column_id}`, c);
    return m;
  }, [table.cells]);

  const eligibleCount = useMemo(() => {
    if (pickedColumnIds.size === 0 || targetRowIds.length === 0) return 0;
    let n = 0;
    for (const rowId of targetRowIds) {
      for (const colId of pickedColumnIds) {
        const cell = cellMap.get(`${rowId}:${colId}`);
        const status = cell?.status ?? "empty";
        const include =
          mode === "all"
            ? true
            : mode === "failed"
              ? status === "failed"
              : status !== "generated";
        if (include) n++;
      }
    }
    return n;
  }, [pickedColumnIds, targetRowIds, cellMap, mode]);

  const providerSummary = useMemo(() => {
    const variants = new Set<string>();
    for (const id of pickedColumnIds) {
      const col = table.columns.find((c) => c.id === id);
      if (!col) continue;
      const p = col.provider_code ?? t("queue.workspaceDefault");
      const m = col.model ?? t("queue.defaultModel");
      variants.add(`${p} / ${m}`);
    }
    return Array.from(variants);
  }, [pickedColumnIds, table.columns, t]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit() {
    if (eligibleCount === 0) return;
    setBusy(true);
    setError(null);
    try {
      const payload: GenerateRequestPayload = {
        column_ids: Array.from(pickedColumnIds),
        row_ids: targetRowIds,
        mode,
      };
      const r = await enqueueGeneration(table.id, payload);
      onEnqueued(r.message);
      onClose();
    } catch (err) {
      console.error("[Queue] enqueue failed", err);
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    setRangeEnd((cur) => Math.min(Math.max(cur, 1), Math.max(1, table.rows.length)));
  }, [table.rows.length]);

  const noPromptColumns = outputCols.filter((c) => c.prompt_id == null);

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("queue.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("queue.subtitle")}
      </p>

      <section className="mt-5">
        <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("queue.columnsToRun")}
        </h3>
        {outputCols.length === 0 ? (
          <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            {t("queue.noOutputColumns")}
          </p>
        ) : (
          <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-md border border-neutral-200 p-2 dark:border-neutral-800">
            {outputCols.map((c) => {
              const runnable = c.prompt_id != null;
              const checked = pickedColumnIds.has(c.id);
              return (
                <li key={c.id}>
                  <label
                    className={
                      "flex items-center gap-2 rounded px-2 py-1 text-sm " +
                      (runnable
                        ? "cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800"
                        : "opacity-50")
                    }
                  >
                    <input
                      type="checkbox"
                      disabled={!runnable}
                      checked={checked && runnable}
                      onChange={() => runnable && toggleColumn(c.id)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="flex-1 truncate text-neutral-900 dark:text-neutral-100">
                      {c.name}
                    </span>
                    {!runnable && (
                      <span className="text-[10px] uppercase text-neutral-500 dark:text-neutral-400">
                        {t("queue.noPrompt")}
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        {noPromptColumns.length > 0 && (
          <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
            {t("queue.noPromptColumnsHint", { count: noPromptColumns.length })}
          </p>
        )}
      </section>

      <section className="mt-5">
        <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("queue.rows")}
        </h3>
        <div className="mt-2 space-y-2">
          <RowOption
            value="all"
            current={rowMode}
            onChange={setRowMode}
            label={t("queue.rowsAll", { count: table.rows.length })}
          />
          <RowOption
            value="selected"
            current={rowMode}
            onChange={setRowMode}
            disabled={preselectedRowIds.length === 0}
            label={
              preselectedRowIds.length > 0
                ? t("queue.rowsSelected", { count: preselectedRowIds.length })
                : t("queue.rowsSelectedNone")
            }
          />
          <RowOption
            value="range"
            current={rowMode}
            onChange={setRowMode}
            label={t("queue.rowsRange")}
          >
            <span className="ml-2 inline-flex items-center gap-1 text-xs">
              {t("queue.fromRow")}
              <input
                type="number"
                min={1}
                max={table.rows.length}
                value={rangeStart}
                onChange={(e) => setRangeStart(Number(e.target.value) || 1)}
                disabled={rowMode !== "range"}
                className="w-16 rounded-md border border-neutral-300 px-2 py-1 text-xs disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
              />
              {t("queue.toRow")}
              <input
                type="number"
                min={1}
                max={table.rows.length}
                value={rangeEnd}
                onChange={(e) => setRangeEnd(Number(e.target.value) || 1)}
                disabled={rowMode !== "range"}
                className="w-16 rounded-md border border-neutral-300 px-2 py-1 text-xs disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
              />
            </span>
          </RowOption>
        </div>
      </section>

      <section className="mt-5">
        <h3 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("queue.whichCells")}
        </h3>
        <div className="mt-2 space-y-1">
          <ModeOption
            value="empty"
            current={mode}
            onChange={setMode}
            label={t("queue.onlyEmpty")}
            hint={t("queue.onlyEmptyHint")}
          />
          <ModeOption
            value="failed"
            current={mode}
            onChange={setMode}
            label={t("queue.onlyFailed")}
            hint={t("queue.onlyFailedHint")}
          />
          <ModeOption
            value="all"
            current={mode}
            onChange={setMode}
            label={t("queue.allCells")}
            hint={t("queue.allCellsHint")}
          />
        </div>
      </section>

      <section className="mt-5 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-950">
        <p className="text-neutral-700 dark:text-neutral-300">
          {t("queue.willGenerate", {
            count: eligibleCount.toLocaleString(),
            cols: pickedColumnIds.size,
            rows: targetRowIds.length,
          })}
        </p>
        {providerSummary.length > 0 && (
          <p className="mt-1 truncate text-neutral-500 dark:text-neutral-400">
            {t("queue.using", { variants: providerSummary.join(", ") })}
          </p>
        )}
      </section>

      {error != null && (
        <div className="mt-3">
          <ErrorPanel title={t("queue.failedToEnqueue")} error={error} />
        </div>
      )}

      <div className="mt-5 flex items-center justify-end gap-3 border-t border-neutral-200 pt-4 dark:border-neutral-800">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          {t("common.cancel")}
        </button>
        <button
          type="button"
          onClick={onSubmit}
          disabled={busy || eligibleCount === 0}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {busy
            ? t("queue.starting")
            : eligibleCount > 0
              ? t("queue.startWithCount", { count: eligibleCount })
              : t("queue.start")}
        </button>
      </div>
    </Modal>
  );
}

function RowOption<V extends string>({
  value,
  current,
  onChange,
  label,
  disabled,
  children,
}: {
  value: V;
  current: V;
  onChange: (v: V) => void;
  label: string;
  disabled?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <label
      className={
        "flex items-center gap-2 text-sm " +
        (disabled ? "opacity-50" : "cursor-pointer")
      }
    >
      <input
        type="radio"
        checked={current === value}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="h-3.5 w-3.5"
      />
      <span className="text-neutral-800 dark:text-neutral-200">{label}</span>
      {children}
    </label>
  );
}

function ModeOption({
  value,
  current,
  onChange,
  label,
  hint,
}: {
  value: GenerateMode;
  current: GenerateMode;
  onChange: (v: GenerateMode) => void;
  label: string;
  hint: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm">
      <input
        type="radio"
        checked={current === value}
        onChange={() => onChange(value)}
        className="mt-0.5 h-3.5 w-3.5"
      />
      <span>
        <span className="text-neutral-800 dark:text-neutral-200">{label}</span>
        <span className="ml-2 text-xs text-neutral-500 dark:text-neutral-400">{hint}</span>
      </span>
    </label>
  );
}
