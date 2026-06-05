"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { Pagination } from "@/components/Pagination";
import { ApiError } from "@/lib/api";
import {
  deleteReplaceRun,
  findInTable,
  listReplaceRuns,
  pairCounts,
  renameReplaceRun,
  replaceInTable,
  splitPairs,
  type FindReplaceConfig,
  type FindResponse,
  type FindReplaceRunRead,
  type MatchedCell,
} from "@/lib/findReplace";
import { RunRowActions } from "@/components/RunRowActions";
import { useT } from "@/lib/i18n-context";
import { getTable, upsertCells } from "@/lib/library";
import type { BulkColumn, BulkTable } from "@/lib/types";

type Mode = "find" | "replace";
const PAGE_SIZE = 25;

export default function FindReplacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tableId = Number(id);
  const { t } = useT();

  const [table, setTable] = useState<BulkTable | null>(null);
  const [mode, setMode] = useState<Mode>("find");
  const [pattern, setPattern] = useState("");
  const [replacement, setReplacement] = useState("");
  const [isRegex, setIsRegex] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(true);
  const [wholeCell, setWholeCell] = useState(false);
  const [columnIds, setColumnIds] = useState<Set<number>>(new Set());

  const [result, setResult] = useState<FindResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<FindReplaceRunRead[]>([]);
  const [editing, setEditing] = useState<MatchedCell | null>(null);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId).then(setTable).catch((e) => setError(String(e)));
  }, [tableId]);

  const loadRuns = useCallback(() => {
    listReplaceRuns(tableId).then(setRuns).catch(() => {});
  }, [tableId]);

  useEffect(() => loadRuns(), [loadRuns]);

  function config(): FindReplaceConfig {
    return {
      pattern,
      replacement,
      is_regex: isRegex,
      case_sensitive: caseSensitive,
      whole_cell: wholeCell,
      column_ids: Array.from(columnIds),
    };
  }

  const counts = pairCounts(pattern, replacement);
  const multi = counts.finds > 1;

  const runFind = useCallback(
    async (page = 1) => {
      if (!pattern) return;
      setBusy(true);
      setError(null);
      try {
        const res = await findInTable(tableId, {
          ...config(),
          page,
          page_size: PAGE_SIZE,
        });
        setResult(res);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        setResult(null);
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tableId, pattern, replacement, isRegex, caseSensitive, wholeCell, columnIds],
  );

  async function runReplace() {
    if (!pattern) return;
    if (counts.mismatch) {
      setError(
        t("findReplace.mismatchError", {
          finds: counts.finds,
          replaces: counts.replaces,
        }),
      );
      return;
    }
    const msg =
      counts.finds > 1
        ? t("findReplace.confirmReplaceMulti", { n: counts.finds })
        : t("findReplace.confirmReplace", { pattern, replacement });
    if (!window.confirm(msg)) return;
    setBusy(true);
    setError(null);
    try {
      const run = await replaceInTable(tableId, config());
      // Redirect to the run page where the before/after table + revert live.
      window.location.href = `/library/${tableId}/find-replace/runs/${run.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  async function saveEdit(next: string) {
    if (!editing) return;
    await upsertCells(tableId, [
      {
        row_id: editing.row_id,
        column_id: editing.column_id,
        value: next === "" ? null : next,
      },
    ]);
    setEditing(null);
    // Re-run find so counts/values reflect the manual edit.
    await runFind(result?.page ?? 1);
  }

  const columns = table?.columns ?? [];
  const columnKind = (colId: number): BulkColumn["kind"] =>
    columns.find((c) => c.id === colId)?.kind ?? "input";

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("findReplace.backToTable")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("findReplace.title")}
      </h1>
      {table && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("findReplace.onTable", { name: table.name })}
        </p>
      )}

      {/* ---- config ---- */}
      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        {/* mode toggle */}
        <div className="inline-flex rounded-md border border-neutral-300 p-0.5 text-xs dark:border-neutral-700">
          {(["find", "replace"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={
                "rounded px-3 py-1 font-medium " +
                (mode === m
                  ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "text-neutral-600 dark:text-neutral-400")
              }
            >
              {m === "find"
                ? t("findReplace.modeFind")
                : t("findReplace.modeReplace")}
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-3">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t("findReplace.multiHint")}
          </p>
          <label className="block">
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("findReplace.patternLabel")}
            </span>
            <textarea
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder={t("findReplace.patternPlaceholder")}
              rows={Math.min(8, Math.max(2, counts.finds || 2))}
              className="mt-1 w-full resize-y rounded-md border border-neutral-300 px-3 py-1.5 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>

          {mode === "replace" && (
            <label className="block">
              <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("findReplace.replacementLabel")}
              </span>
              <textarea
                value={replacement}
                onChange={(e) => setReplacement(e.target.value)}
                placeholder={t("findReplace.replacementPlaceholder")}
                rows={Math.min(8, Math.max(2, counts.replaces || 2))}
                className="mt-1 w-full resize-y rounded-md border border-neutral-300 px-3 py-1.5 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900"
              />
              {multi && (
                <span
                  className={
                    "mt-1 block text-xs " +
                    (counts.mismatch
                      ? "text-red-600 dark:text-red-400"
                      : "text-neutral-500 dark:text-neutral-400")
                  }
                >
                  {counts.replaces === 0
                    ? t("findReplace.pairDeleteAll", { finds: counts.finds })
                    : counts.mismatch
                      ? t("findReplace.mismatchError", {
                          finds: counts.finds,
                          replaces: counts.replaces,
                        })
                      : t("findReplace.pairOk", { n: counts.finds })}
                </span>
              )}
            </label>
          )}

          {/* options */}
          <div className="flex flex-wrap gap-4 text-xs text-neutral-700 dark:text-neutral-300">
            <Toggle
              checked={isRegex}
              onChange={setIsRegex}
              label={t("findReplace.optRegex")}
            />
            <Toggle
              checked={caseSensitive}
              onChange={setCaseSensitive}
              label={t("findReplace.optCase")}
            />
            <Toggle
              checked={wholeCell}
              onChange={setWholeCell}
              label={t("findReplace.optWholeCell")}
            />
          </div>

          {/* column scope */}
          <div>
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("findReplace.columnsLabel")}
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setColumnIds(new Set())}
                className={
                  "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                  (columnIds.size === 0
                    ? "bg-neutral-900 text-white ring-neutral-900 dark:bg-neutral-100 dark:text-neutral-900 dark:ring-neutral-100"
                    : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                }
              >
                {t("findReplace.allColumns")}
              </button>
              {columns.map((c) => {
                const on = columnIds.has(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() =>
                      setColumnIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(c.id)) next.delete(c.id);
                        else next.add(c.id);
                        return next;
                      })
                    }
                    className={
                      "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                      (on
                        ? "bg-blue-600 text-white ring-blue-600"
                        : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                    }
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* actions */}
          <div className="mt-1 flex items-center gap-2">
            <button
              type="button"
              disabled={!pattern || busy}
              onClick={() => runFind(1)}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {mode === "replace"
                ? t("findReplace.previewBtn")
                : t("findReplace.findBtn")}
            </button>
            {mode === "replace" && (
              <button
                type="button"
                disabled={!pattern || busy || counts.mismatch}
                onClick={runReplace}
                className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
              >
                {t("findReplace.replaceBtn")}
              </button>
            )}
          </div>
        </div>
      </section>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {/* ---- results ---- */}
      {result && (
        <section className="mt-5">
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            {t("findReplace.summary", {
              matches: result.total_matches,
              cells: result.total_cells,
            })}
          </p>
          {result.total_cells > 0 && (
            <>
              <div className="mt-3 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">
                        {t("findReplace.colRow")}
                      </th>
                      <th className="px-3 py-2 font-medium">
                        {t("findReplace.colColumn")}
                      </th>
                      <th className="px-3 py-2 font-medium">
                        {t("findReplace.colValue")}
                      </th>
                      <th className="px-3 py-2 text-right font-medium">
                        {t("findReplace.colMatches")}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                    {result.items.map((m) => (
                      <tr
                        key={`${m.row_id}:${m.column_id}`}
                        onClick={() => setEditing(m)}
                        className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-900"
                      >
                        <td className="px-3 py-2 tabular-nums text-neutral-500">
                          #{m.row_position + 1}
                        </td>
                        <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                          {m.column_name}
                        </td>
                        <td className="max-w-md truncate px-3 py-2 text-neutral-800 dark:text-neutral-200">
                          {m.value}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-neutral-500">
                          {m.match_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={result.page}
                pageSize={result.page_size}
                total={result.total_cells}
                onPage={(p) => runFind(p)}
              />
            </>
          )}
        </section>
      )}

      {/* ---- replace history ---- */}
      {runs.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("findReplace.historyHeading")}
          </h2>
          <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {runs.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/library/${tableId}/find-replace/runs/${r.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="min-w-0 truncate">
                    {r.name && (
                      <span className="mr-2 font-medium text-neutral-800 dark:text-neutral-200">
                        {r.name}
                      </span>
                    )}
                    {(() => {
                      const pairs = splitPairs(r.pattern, r.replacement);
                      const first = pairs[0];
                      return (
                        <>
                          <code className="text-neutral-800 dark:text-neutral-200">
                            {first?.find}
                          </code>
                          <span className="text-neutral-400"> → </span>
                          <code className="text-neutral-800 dark:text-neutral-200">
                            {first?.replace || "∅"}
                          </code>
                          {pairs.length > 1 && (
                            <span className="ml-2 text-xs text-neutral-400">
                              {t("findReplace.morePairs", {
                                n: pairs.length - 1,
                              })}
                            </span>
                          )}
                        </>
                      );
                    })()}
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs text-neutral-500">
                    {t("findReplace.historyCells", { n: r.cell_count })}
                    {r.status === "reverted" && (
                      <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                        {t("findReplace.reverted")}
                      </span>
                    )}
                    <RunRowActions
                      name={r.name}
                      onRename={async (n) => {
                        await renameReplaceRun(r.id, n);
                        loadRuns();
                      }}
                      onDelete={async () => {
                        await deleteReplaceRun(r.id);
                        loadRuns();
                      }}
                    />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {editing && (
        <CellEditorModal
          title={`${editing.column_name} · #${editing.row_position + 1}`}
          initialValue={editing.value}
          defaultMode={columnKind(editing.column_id) === "output" ? "preview" : "edit"}
          onClose={() => setEditing(null)}
          onSave={saveEdit}
        />
      )}
    </main>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-1.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
      />
      {label}
    </label>
  );
}
