"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { RunRowActions } from "@/components/RunRowActions";
import { ChangeDiff } from "@/components/StructureFormatDiff";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable } from "@/lib/library";
import {
  applyStructureFormat,
  deleteStructureFormatRun,
  listStructureFormatRuns,
  previewStructureFormat,
  renameStructureFormatRun,
  SF_OPERATIONS,
  type StructureFormatOp,
  type StructureFormatPreview,
  type StructureFormatRunRead,
} from "@/lib/structureFormat";
import type { BulkTable } from "@/lib/types";

const PREVIEW_PAGE_SIZE = 10;

export default function StructureFormatPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tableId = Number(id);
  const { t } = useT();
  const router = useRouter();

  const [table, setTable] = useState<BulkTable | null>(null);
  const [ops, setOps] = useState<Set<StructureFormatOp>>(new Set());
  const [columnIds, setColumnIds] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<"" | "preview" | "apply">("");
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<StructureFormatPreview | null>(null);
  const [runs, setRuns] = useState<StructureFormatRunRead[]>([]);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    // Only the name + columns are needed (both come back in full); a 1-row
    // page keeps a large table's cells out of the payload.
    getTable(tableId, { page: 1, page_size: 1 })
      .then(setTable)
      .catch((e) => setError(String(e)));
  }, [tableId]);

  const loadRuns = useCallback(() => {
    listStructureFormatRuns(tableId).then(setRuns).catch(() => {});
  }, [tableId]);
  useEffect(() => loadRuns(), [loadRuns]);

  const columns = table?.columns ?? [];
  const canRun = ops.size > 0 && columnIds.size > 0;
  // Operations in canonical order (selection is a subset).
  const orderedOps = () => SF_OPERATIONS.filter((o) => ops.has(o));

  function toggleOp(op: StructureFormatOp) {
    setPreview(null);
    setOps((prev) => {
      const next = new Set(prev);
      if (next.has(op)) next.delete(op);
      else next.add(op);
      return next;
    });
  }

  function toggleColumn(cid: number) {
    setPreview(null);
    setColumnIds((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  }

  async function loadPreview(p: number) {
    if (!canRun || busy) return;
    setBusy("preview");
    setError(null);
    try {
      const pv = await previewStructureFormat(
        tableId,
        { operations: orderedOps(), column_ids: Array.from(columnIds) },
        p,
        PREVIEW_PAGE_SIZE,
      );
      setPreview(pv);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function run() {
    if (!canRun || busy) return;
    if (!window.confirm(t("structureFormat.confirmApply"))) return;
    setBusy("apply");
    setError(null);
    try {
      const r = await applyStructureFormat(tableId, {
        operations: orderedOps(),
        column_ids: Array.from(columnIds),
      });
      router.push(`/library/${tableId}/structure-format/runs/${r.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy("");
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("structureFormat.backToTable")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("structureFormat.title")}
      </h1>
      {table && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("structureFormat.onTable", { name: table.name })}
        </p>
      )}

      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        {/* operations (run in the listed order) */}
        <div>
          <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("structureFormat.opsLabel")}
          </span>
          <p className="mt-0.5 text-xs text-neutral-400 dark:text-neutral-500">
            {t("structureFormat.opsHint")}
          </p>
          <div className="mt-2 grid gap-2">
            {SF_OPERATIONS.map((op, i) => (
              <label
                key={op}
                className="flex cursor-pointer items-start gap-2 rounded-md border border-neutral-200 p-2.5 text-sm hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-800/50"
              >
                <input
                  type="checkbox"
                  checked={ops.has(op)}
                  onChange={() => toggleOp(op)}
                  className="mt-0.5 h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
                />
                <span>
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">
                    {i + 1}. {t(`structureFormat.op.${op}.title` as never)}
                  </span>
                  <span className="block text-xs text-neutral-500 dark:text-neutral-400">
                    {t(`structureFormat.op.${op}.desc` as never)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* columns to clean */}
        <div className="mt-4">
          <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("structureFormat.columnsLabel")}
          </span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {columns.map((c) => {
              const on = columnIds.has(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleColumn(c.id)}
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

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canRun || busy !== ""}
            onClick={() => loadPreview(1)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {busy === "preview" ? t("common.loading") : t("structureFormat.previewBtn")}
          </button>
          <button
            type="button"
            disabled={!canRun || busy !== ""}
            onClick={run}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {busy === "apply" ? t("common.loading") : t("structureFormat.applyBtn")}
          </button>
          {preview && (
            <span className="text-xs text-neutral-600 dark:text-neutral-400">
              {t("structureFormat.previewResult", {
                change: preview.would_change,
                total: preview.candidates,
              })}
            </span>
          )}
        </div>
      </section>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {/* preview scope — the cells that would change, before applying */}
      {preview && (
        <section className="mt-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("structureFormat.previewHeading")}
          </h2>
          {preview.would_change === 0 ? (
            <p className="mt-2 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {t("structureFormat.previewNone")}
            </p>
          ) : (
            <>
              <div className="mt-2 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">{t("findReplace.colRow")}</th>
                      <th className="px-3 py-2 font-medium">{t("findReplace.colColumn")}</th>
                      <th className="px-3 py-2 font-medium">{t("structureFormatRun.colApplied")}</th>
                      <th className="px-3 py-2 font-medium">{t("structureFormatRun.colChanges")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                    {preview.items.map((c) => (
                      <tr
                        key={`${c.row_id}:${c.column_id}`}
                        className="align-top"
                      >
                        <td className="px-3 py-2 tabular-nums text-neutral-500">
                          #{c.row_position + 1}
                        </td>
                        <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                          {c.column_name}
                        </td>
                        <td className="px-3 py-2">
                          <span className="flex flex-wrap gap-1">
                            {c.applied_ops.map((o) => (
                              <span
                                key={o}
                                className="whitespace-nowrap rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-500/30"
                              >
                                {t(`structureFormat.op.${o}.title` as never)}
                              </span>
                            ))}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                          <ChangeDiff segments={c.change_segments} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={preview.page}
                pageSize={preview.page_size}
                total={preview.would_change}
                onPage={(p) => loadPreview(p)}
              />
            </>
          )}
        </section>
      )}

      {runs.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("structureFormat.historyHeading")}
          </h2>
          <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {runs.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/library/${tableId}/structure-format/runs/${r.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-300">
                    {r.name || t("structureFormat.runLabel", { id: r.id })}
                    <span className="ml-2 text-xs text-neutral-400">
                      {r.operations
                        .map((o) => t(`structureFormat.op.${o}.title` as never))
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    {r.reverted_at && (
                      <span className="text-amber-600 dark:text-amber-400">
                        {t("structureFormat.reverted")}
                      </span>
                    )}
                    <span className="text-neutral-500 dark:text-neutral-400">
                      {t("structureFormat.historyCells", { n: r.cell_count })}
                    </span>
                    <LinkCheckStatusChip status={r.status} />
                    <RunRowActions
                      name={r.name}
                      canDelete={r.status !== "queued" && r.status !== "running"}
                      onRename={async (n) => {
                        await renameStructureFormatRun(r.id, n);
                        loadRuns();
                      }}
                      onDelete={async () => {
                        await deleteStructureFormatRun(r.id);
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
    </main>
  );
}
