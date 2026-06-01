"use client";

import { use, useCallback, useEffect, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { Pagination } from "@/components/Pagination";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import {
  getReplaceRun,
  revertReplaceRun,
  type FindReplaceRunDetail,
  type HighlightSegment,
  type ReplacedCell,
} from "@/lib/findReplace";
import { useT } from "@/lib/i18n-context";
import { getTable, upsertCells } from "@/lib/library";
import type { BulkColumn } from "@/lib/types";

const PAGE_SIZE = 25;

export default function ReplaceRunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [run, setRun] = useState<FindReplaceRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [reverting, setReverting] = useState(false);
  const [editing, setEditing] = useState<ReplacedCell | null>(null);
  const [columns, setColumns] = useState<BulkColumn[]>([]);

  const load = useCallback(
    async (p: number) => {
      try {
        const r = await getReplaceRun(rid, p, PAGE_SIZE);
        setRun(r);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      }
    },
    [rid],
  );

  useEffect(() => {
    if (!Number.isFinite(rid)) return;
    void load(page);
  }, [rid, page, load]);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId).then((tb) => setColumns(tb.columns)).catch(() => {});
  }, [tableId]);

  async function onRevert() {
    if (!run) return;
    const msg =
      run.drifted_count > 0
        ? t("replaceRun.confirmRevertDrift", { n: run.drifted_count })
        : t("replaceRun.confirmRevert");
    if (!window.confirm(msg)) return;
    setReverting(true);
    try {
      await revertReplaceRun(run.id);
      await load(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setReverting(false);
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
    await load(page);
  }

  const columnKind = (colId: number): BulkColumn["kind"] =>
    columns.find((c) => c.id === colId)?.kind ?? "input";

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("findReplace.title"),
            href: `/library/${tableId}/find-replace`,
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
                {t("replaceRun.title", { id: run.id })}
              </h1>
              <p className="mt-1 break-all text-sm">
                <code className="rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
                  {run.pattern}
                </code>
                <span className="px-1.5 text-neutral-400">→</span>
                <code className="rounded bg-neutral-100 px-1.5 py-0.5 dark:bg-neutral-800">
                  {run.replacement || "∅"}
                </code>
              </p>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("replaceRun.meta", {
                  cells: run.cell_count,
                  matches: run.match_count,
                  by: run.created_by_name ?? "—",
                  when: new Date(run.created_at).toLocaleString(),
                })}
                {run.is_regex && ` · ${t("findReplace.optRegex")}`}
                {!run.case_sensitive && ` · ${t("replaceRun.caseInsensitive")}`}
                {run.whole_cell && ` · ${t("findReplace.optWholeCell")}`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {run.status === "reverted" ? (
                <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                  {t("replaceRun.revertedAt", {
                    when: run.reverted_at
                      ? new Date(run.reverted_at).toLocaleString()
                      : "",
                  })}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={onRevert}
                  disabled={reverting}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {reverting ? t("common.loading") : t("replaceRun.revert")}
                </button>
              )}
            </div>
          </header>

          {run.status === "applied" && run.drifted_count > 0 && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-inset ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25">
              {t("replaceRun.driftWarning", { n: run.drifted_count })}
            </p>
          )}

          <div className="mt-5 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("findReplace.colRow")}</th>
                  <th className="px-3 py-2 font-medium">{t("findReplace.colColumn")}</th>
                  <th className="px-3 py-2 font-medium">{t("replaceRun.colBefore")}</th>
                  <th className="px-3 py-2 font-medium">{t("replaceRun.colAfter")}</th>
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
                    <td className="max-w-xs px-3 py-2 text-neutral-600 dark:text-neutral-400">
                      <span className="block max-h-20 overflow-hidden whitespace-pre-wrap break-words">
                        <Segments segments={c.old_segments} side="old" />
                      </span>
                    </td>
                    <td className="max-w-xs px-3 py-2 text-neutral-800 dark:text-neutral-200">
                      <span className="block max-h-20 overflow-hidden whitespace-pre-wrap break-words">
                        <Segments
                          segments={c.new_segments}
                          side={c.drifted ? "drift" : "new"}
                        />
                      </span>
                      {c.drifted && (
                        <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">
                          {t("replaceRun.editedSince")}
                        </span>
                      )}
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

/** Renders a before/after value as styled runs. "old" side: matched span
 *  struck through in red. "new" side: inserted replacement bold green.
 *  "drift" side: a later manual edit, bold amber (matches the "edited since"
 *  badge). Unchanged text stays neutral. */
function Segments({
  segments,
  side,
}: {
  segments: HighlightSegment[];
  side: "old" | "new" | "drift";
}) {
  const changedCls =
    side === "old"
      ? "bg-transparent text-red-500 line-through decoration-red-400/70 dark:text-red-400"
      : side === "drift"
        ? "bg-transparent font-semibold text-amber-800 dark:text-amber-200"
        : "bg-transparent font-semibold text-green-600 dark:text-green-400";
  return (
    <>
      {segments.map((s, i) =>
        s.changed ? (
          <mark key={i} className={changedCls}>
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}
