"use client";

import { useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { listEnabledProviders } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import {
  enqueueGeneration,
  generatePreview,
  type GenerateMode,
  type GenerateRequestPayload,
} from "@/lib/library";
import type { BulkTable, EnabledProvider } from "@/lib/types";

interface Props {
  table: BulkTable;
  /** Total rows in the whole table (the modal only holds the current page). */
  totalRowCount: number;
  /** True when the grid is in "select all N" mode. */
  allRowsSelected: boolean;
  preselectedRowIds: number[];
  /** Seed the cell filter (e.g. "failed" when opened from the error banner).
   *  Defaults to "empty". */
  initialMode?: GenerateMode;
  /** Preselect these columns instead of every runnable one — the error banner
   *  passes just the columns that actually have the problem. Non-runnable ids
   *  are dropped; an empty result falls back to all runnable columns. */
  initialColumnIds?: number[];
  onClose: () => void;
  onEnqueued: (message: string) => void;
}

type RowMode = "all" | "range" | "selected";

export function GenerationQueueModal({
  table,
  totalRowCount,
  allRowsSelected,
  preselectedRowIds,
  initialMode,
  initialColumnIds,
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
  const [pickedColumnIds, setPickedColumnIds] = useState<Set<number>>(() => {
    if (initialColumnIds && initialColumnIds.length > 0) {
      const runnable = new Set(runnableColumnIds);
      const picked = new Set(initialColumnIds.filter((id) => runnable.has(id)));
      if (picked.size > 0) return picked;
    }
    return new Set(runnableColumnIds);
  });

  function toggleColumn(id: number) {
    setPickedColumnIds((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // "selected" only makes sense when there's an explicit page selection and
  // we're NOT in select-all-N mode (which is effectively "all").
  const [rowMode, setRowMode] = useState<RowMode>(
    !allRowsSelected && preselectedRowIds.length > 0 ? "selected" : "all",
  );
  const [rangeStart, setRangeStart] = useState(1);
  const [rangeEnd, setRangeEnd] = useState(totalRowCount);

  const [mode, setMode] = useState<GenerateMode>(initialMode ?? "empty");

  // Build the request payload from the row mode. Row targeting is resolved
  // server-side now (the modal no longer holds every row): 'all' omits row
  // refs, 'range' sends an ordinal row_range, 'selected' sends explicit ids.
  const basePayload = useMemo<GenerateRequestPayload>(() => {
    const p: GenerateRequestPayload = {
      column_ids: Array.from(pickedColumnIds),
      mode,
    };
    if (rowMode === "selected") {
      p.row_ids = preselectedRowIds;
    } else if (rowMode === "range") {
      const start = Math.max(1, rangeStart);
      const end = Math.max(start, Math.min(rangeEnd, totalRowCount));
      p.row_range = { start, end };
    }
    return p;
  }, [pickedColumnIds, mode, rowMode, rangeStart, rangeEnd, preselectedRowIds, totalRowCount]);

  // "Will generate N" — fetched from the server so the count matches what the
  // enqueue would actually do, without scanning every cell client-side.
  const [preview, setPreview] = useState<{ will_generate: number; skipped: number } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  useEffect(() => {
    if (pickedColumnIds.size === 0) {
      setPreview({ will_generate: 0, skipped: 0 });
      return;
    }
    if (rowMode === "selected" && preselectedRowIds.length === 0) {
      setPreview({ will_generate: 0, skipped: 0 });
      return;
    }
    let ignored = false;
    setPreviewLoading(true);
    const h = setTimeout(() => {
      generatePreview(table.id, basePayload)
        .then((r) => {
          if (!ignored) setPreview(r);
        })
        .catch(() => {
          if (!ignored) setPreview(null);
        })
        .finally(() => {
          if (!ignored) setPreviewLoading(false);
        });
    }, 300);
    return () => {
      ignored = true;
      clearTimeout(h);
    };
  }, [table.id, basePayload, pickedColumnIds.size, rowMode, preselectedRowIds.length]);

  const eligibleCount = preview?.will_generate ?? 0;

  // Targeted row count for the summary line (independent of cell filtering).
  const targetRowCount = useMemo(() => {
    if (rowMode === "selected") return preselectedRowIds.length;
    if (rowMode === "range") {
      const start = Math.max(1, rangeStart);
      const end = Math.max(start, Math.min(rangeEnd, totalRowCount));
      return Math.max(0, end - start + 1);
    }
    return totalRowCount;
  }, [rowMode, preselectedRowIds.length, rangeStart, rangeEnd, totalRowCount]);

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

  // Queue-wide override: when on, every cell in this run uses the same
  // provider+model regardless of per-column settings. Off by default — most
  // runs just use what's configured on each column.
  const [overrideEnabled, setOverrideEnabled] = useState(false);
  const [providers, setProviders] = useState<EnabledProvider[] | null>(null);
  const [overrideProvider, setOverrideProvider] = useState<string | null>(null);
  const [overrideModel, setOverrideModel] = useState<string | null>(null);

  // Load providers lazily on first enable.
  useEffect(() => {
    if (!overrideEnabled || providers !== null) return;
    let ignored = false;
    listEnabledProviders()
      .then((list) => {
        if (ignored) return;
        setProviders(list);
        const first = list.find((p) => p.has_api_key) ?? list[0] ?? null;
        if (first && overrideProvider === null) {
          setOverrideProvider(first.code);
          setOverrideModel(first.default_model ?? first.available_models[0] ?? null);
        }
      })
      .catch(() => {
        if (!ignored) setProviders([]);
      });
    return () => {
      ignored = true;
    };
  }, [overrideEnabled, providers, overrideProvider]);

  const overrideProviderObj = useMemo(
    () => providers?.find((p) => p.code === overrideProvider) ?? null,
    [providers, overrideProvider],
  );

  // When the user picks a different override provider, default the model.
  useEffect(() => {
    if (!overrideEnabled || !overrideProviderObj) return;
    setOverrideModel(
      overrideProviderObj.default_model ??
        overrideProviderObj.available_models[0] ??
        null,
    );
  }, [overrideEnabled, overrideProviderObj]);

  const overrideValid =
    !overrideEnabled || (!!overrideProvider && !!overrideModel);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onSubmit() {
    if (eligibleCount === 0) return;
    if (!overrideValid) return;
    setBusy(true);
    setError(null);
    try {
      const payload: GenerateRequestPayload = { ...basePayload };
      if (overrideEnabled && overrideProvider && overrideModel) {
        payload.override_provider_code = overrideProvider;
        payload.override_model = overrideModel;
      }
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
    setRangeEnd((cur) => Math.min(Math.max(cur, 1), Math.max(1, totalRowCount)));
  }, [totalRowCount]);

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
            label={t("queue.rowsAll", { count: totalRowCount })}
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
                max={totalRowCount}
                value={rangeStart}
                onChange={(e) => setRangeStart(Number(e.target.value) || 1)}
                disabled={rowMode !== "range"}
                className="w-16 rounded-md border border-neutral-300 px-2 py-1 text-xs disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
              />
              {t("queue.toRow")}
              <input
                type="number"
                min={1}
                max={totalRowCount}
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
            value="truncated"
            current={mode}
            onChange={setMode}
            label={t("queue.onlyTruncated")}
            hint={t("queue.onlyTruncatedHint")}
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

      {/* Queue-wide provider/model override */}
      <section className="mt-5">
        <label className="flex cursor-pointer items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={overrideEnabled}
            onChange={(e) => setOverrideEnabled(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5"
          />
          <span>
            <span className="font-medium text-neutral-800 dark:text-neutral-200">
              {t("queue.overrideLabel")}
            </span>
            <span className="ml-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("queue.overrideHint")}
            </span>
          </span>
        </label>
        {overrideEnabled && (
          <div className="mt-2 grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-0.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("queue.overrideProvider")}
              </span>
              <select
                value={overrideProvider ?? ""}
                onChange={(e) => setOverrideProvider(e.target.value || null)}
                disabled={!providers}
                className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {providers === null && <option value="">{t("common.loading")}</option>}
                {(providers ?? []).map((p) => (
                  <option key={p.code} value={p.code} disabled={!p.has_api_key}>
                    {p.display_name}
                    {!p.has_api_key && t("queue.overrideNoKey")}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-0.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("queue.overrideModel")}
              </span>
              <select
                value={overrideModel ?? ""}
                onChange={(e) => setOverrideModel(e.target.value || null)}
                disabled={!overrideProviderObj}
                className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {(overrideProviderObj?.available_models ?? []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </section>

      <section className="mt-5 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-950">
        <p className="text-neutral-700 dark:text-neutral-300">
          {t("queue.willGenerate", {
            count: previewLoading ? "…" : eligibleCount.toLocaleString(),
            cols: pickedColumnIds.size,
            rows: targetRowCount,
          })}
        </p>
        {overrideEnabled && overrideProvider && overrideModel ? (
          <p className="mt-1 truncate text-neutral-500 dark:text-neutral-400">
            {t("queue.usingOverride", {
              provider: overrideProvider,
              model: overrideModel,
            })}
          </p>
        ) : (
          providerSummary.length > 0 && (
            <p className="mt-1 truncate text-neutral-500 dark:text-neutral-400">
              {t("queue.using", { variants: providerSummary.join(", ") })}
            </p>
          )
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
          disabled={busy || eligibleCount === 0 || !overrideValid}
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
