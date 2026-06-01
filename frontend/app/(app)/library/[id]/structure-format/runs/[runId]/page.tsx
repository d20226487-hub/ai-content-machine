"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { ChangeDiff } from "@/components/StructureFormatDiff";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable, upsertCells } from "@/lib/library";
import {
  cancelStructureFormatRun,
  getStructureFormatRun,
  resumeStructureFormatRun,
  revertStructureFormatRun,
  type StructureFormatCell,
  type StructureFormatOp,
  type StructureFormatRunDetail,
} from "@/lib/structureFormat";
import type { BulkColumn } from "@/lib/types";

const PAGE_SIZE = 25;

export default function StructureFormatRunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [run, setRun] = useState<StructureFormatRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [filterOp, setFilterOp] = useState<StructureFormatOp | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "cancel" | "resume" | "revert">("");
  const [editing, setEditing] = useState<StructureFormatCell | null>(null);
  const [columns, setColumns] = useState<BulkColumn[]>([]);
  const stoppedRef = useRef(false);

  // Changing the filter resets to page 1.
  useEffect(() => {
    setPage(1);
  }, [filterOp]);

  const tick = useCallback(
    async (p: number) => {
      try {
        const r = await getStructureFormatRun(rid, p, PAGE_SIZE, filterOp);
        setRun(r);
        setError(null);
        if (r.status === "done" || r.status === "failed" || r.status === "cancelled") {
          stoppedRef.current = true;
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        stoppedRef.current = true;
      }
    },
    [rid, filterOp],
  );

  // Poll while the run is active; refetch immediately on page change.
  useEffect(() => {
    if (!Number.isFinite(rid)) return;
    stoppedRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick(page);
      if (cancelled || stoppedRef.current) return;
      timer = setTimeout(loop, 2000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [rid, page, tick]);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId, { page: 1, page_size: 1 })
      .then((tb) => setColumns(tb.columns))
      .catch(() => {});
  }, [tableId]);

  async function onCancel() {
    if (!run) return;
    if (!window.confirm(t("structureFormatRun.confirmCancel"))) return;
    setBusy("cancel");
    try {
      await cancelStructureFormatRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function onResume() {
    if (!run) return;
    setBusy("resume");
    try {
      await resumeStructureFormatRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function onRevert() {
    if (!run) return;
    const msg =
      run.drifted_count > 0
        ? t("structureFormatRun.confirmRevertDrift", { n: run.drifted_count })
        : t("structureFormatRun.confirmRevert");
    if (!window.confirm(msg)) return;
    setBusy("revert");
    try {
      await revertStructureFormatRun(run.id);
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function saveEdit(next: string) {
    if (!editing || !run) return;
    await upsertCells(run.table_id, [
      {
        row_id: editing.row_id,
        column_id: editing.column_id,
        value: next === "" ? null : next,
      },
    ]);
    setEditing(null);
    await tick(page);
  }

  const columnKind = (colId: number): BulkColumn["kind"] =>
    columns.find((c) => c.id === colId)?.kind ?? "input";

  const isActive = run?.status === "queued" || run?.status === "running";
  const reverted = !!run?.reverted_at;
  const pct =
    run && run.total > 0
      ? Math.round((run.done / run.total) * 100)
      : run?.status === "running"
        ? 5
        : 0;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("structureFormat.title"),
            href: `/library/${tableId}/structure-format`,
          },
          { label: run?.name ?? t("breadcrumb.run", { id: rid }) },
        ]}
      />

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {run && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {t("structureFormatRun.title", { id: run.id })}
              </h1>
              <p className="mt-1 flex flex-wrap gap-1.5">
                {run.operations.map((o) => (
                  <span
                    key={o}
                    className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                  >
                    {t(`structureFormat.op.${o}.title` as never)}
                  </span>
                ))}
              </p>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("structureFormatRun.meta", {
                  cells: run.cell_count,
                  by: run.created_by_name ?? "—",
                  when: new Date(run.created_at).toLocaleString(),
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <LinkCheckStatusChip status={run.status} />
              {isActive && (
                <>
                  <button
                    type="button"
                    onClick={onResume}
                    disabled={busy !== ""}
                    title={t("structureFormatRun.resumeHint")}
                    className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                  >
                    {busy === "resume" ? t("common.loading") : t("structureFormatRun.resume")}
                  </button>
                  <button
                    type="button"
                    onClick={onCancel}
                    disabled={busy !== ""}
                    className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                  >
                    {busy === "cancel" ? t("common.loading") : t("structureFormatRun.cancel")}
                  </button>
                </>
              )}
              {!isActive && !reverted && run.cell_count > 0 && (
                <button
                  type="button"
                  onClick={onRevert}
                  disabled={busy !== ""}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {busy === "revert" ? t("common.loading") : t("structureFormatRun.revert")}
                </button>
              )}
              {reverted && (
                <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                  {t("structureFormatRun.revertedAt", {
                    when: run.reverted_at
                      ? new Date(run.reverted_at).toLocaleString()
                      : "",
                  })}
                </span>
              )}
            </div>
          </header>

          {/* progress while active */}
          {isActive && (
            <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                {run.total > 0
                  ? t("structureFormatRun.processing", { done: run.done, total: run.total })
                  : t("structureFormatRun.preparing")}
              </p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="h-full bg-blue-500 transition-[width] duration-300 dark:bg-blue-400"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          {run.error && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {run.error}
            </p>
          )}

          {!isActive && run.status === "done" && run.drifted_count > 0 && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-inset ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25">
              {t("structureFormatRun.driftWarning", { n: run.drifted_count })}
            </p>
          )}

          {/* filter by applied operation (only meaningful with >1 op) */}
          {!isActive && run.cell_count > 0 && run.operations.length > 1 && (
            <div className="mt-5 flex items-center gap-2">
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("structureFormatRun.filterLabel")}
              </span>
              <select
                value={filterOp}
                onChange={(e) =>
                  setFilterOp(e.target.value as StructureFormatOp | "")
                }
                className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              >
                <option value="">{t("structureFormatRun.filterAllOps")}</option>
                {run.operations.map((o) => (
                  <option key={o} value={o}>
                    {t(`structureFormat.op.${o}.title` as never)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* results — only once the run produced changed cells */}
          {!isActive && run.total_cells === 0 ? (
            <p className="mt-5 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {filterOp ? t("structureFormatRun.noFilterMatch") : t("structureFormatRun.noChanges")}
            </p>
          ) : run.total_cells > 0 ? (
            <>
              <div className="mt-5 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
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
                    {run.items.map((c) => (
                      <tr
                        key={`${c.row_id}:${c.column_id}`}
                        onClick={() => setEditing(c)}
                        className="cursor-pointer align-top hover:bg-neutral-50 dark:hover:bg-neutral-900"
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
                          {c.drifted &&
                            (reverted ? (
                              <span className="mt-1 inline-block rounded-full bg-neutral-200 px-2 py-0.5 text-[10px] font-medium text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300">
                                {t("replaceRun.revertedRow")}
                              </span>
                            ) : (
                              <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">
                                {t("replaceRun.editedSince")}
                              </span>
                            ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={run.page}
                pageSize={run.page_size}
                total={run.total_cells}
                onPage={setPage}
              />
            </>
          ) : null}
        </>
      )}

      {editing && run && (
        <CellEditorModal
          title={`${editing.column_name} · #${editing.row_position + 1}`}
          initialValue={editing.current_value ?? ""}
          defaultMode={columnKind(editing.column_id) === "output" ? "preview" : "edit"}
          onClose={() => setEditing(null)}
          onSave={saveEdit}
        />
      )}
    </main>
  );
}

