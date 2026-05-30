"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable, upsertCells } from "@/lib/library";
import {
  cancelLinkCheckRun,
  getLinkCheckRun,
  resumeLinkCheckRun,
  type LinkCheckRunDetail,
  type LinkProblem,
  type LinkViolation,
} from "@/lib/linkCheck";
import type { BulkColumn } from "@/lib/types";

const PAGE_SIZE = 25;

export default function LinkCheckRunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [run, setRun] = useState<LinkCheckRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [columns, setColumns] = useState<BulkColumn[]>([]);
  const [cellValues, setCellValues] = useState<Map<string, string>>(new Map());
  const [editing, setEditing] = useState<LinkViolation | null>(null);
  const [filterProblem, setFilterProblem] = useState<LinkProblem | "">("");
  const [filterStatus, setFilterStatus] = useState<number | "">("");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const stoppedRef = useRef(false);

  // Debounce the link search so each keystroke doesn't refetch.
  useEffect(() => {
    const id = setTimeout(() => setQ(qInput), 350);
    return () => clearTimeout(id);
  }, [qInput]);

  // Any filter change resets to page 1.
  useEffect(() => {
    setPage(1);
  }, [filterProblem, filterStatus, q]);

  const tick = useCallback(
    async (p: number) => {
      try {
        const r = await getLinkCheckRun(rid, p, PAGE_SIZE, {
          problem: filterProblem || undefined,
          status_code: filterStatus === "" ? undefined : filterStatus,
          q: q || undefined,
        });
        setRun(r);
        setError(null);
        if (r.status === "done" || r.status === "cancelled" || r.status === "failed") {
          stoppedRef.current = true;
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        stoppedRef.current = true;
      }
    },
    [rid, filterProblem, filterStatus, q],
  );

  // Poll while active; refetch immediately on page or filter change.
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

  const loadCells = useCallback(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId)
      .then((tb) => {
        setColumns(tb.columns);
        const m = new Map<string, string>();
        for (const c of tb.cells) {
          if (c.value != null) m.set(`${c.row_id}:${c.column_id}`, c.value);
        }
        setCellValues(m);
      })
      .catch(() => {});
  }, [tableId]);
  useEffect(() => loadCells(), [loadCells]);

  async function onCancel() {
    if (!run || cancelling) return;
    if (!window.confirm(t("linkCheckRun.confirmCancel"))) return;
    setCancelling(true);
    try {
      await cancelLinkCheckRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCancelling(false);
    }
  }

  async function onResume() {
    if (!run || resuming) return;
    setResuming(true);
    try {
      await resumeLinkCheckRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setResuming(false);
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
    loadCells();
  }

  const columnKind = (colId: number): BulkColumn["kind"] =>
    columns.find((c) => c.id === colId)?.kind ?? "input";

  const isActive = run?.status === "queued" || run?.status === "running";

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4 flex items-center gap-4">
        <Link
          href={`/library/${tableId}/link-check`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("linkCheckRun.backToTool")}
        </Link>
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("linkCheckRun.backToTable")}
        </Link>
      </div>

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {run && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {t("linkCheckRun.title", { id: run.id })}
              </h1>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("linkCheckRun.meta", {
                  by: run.created_by_name ?? "—",
                  when: new Date(run.created_at).toLocaleString(),
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <LinkCheckStatusChip status={run.status} />
              {isActive && run.check_crawl && (
                <button
                  type="button"
                  onClick={onResume}
                  disabled={resuming}
                  title={t("linkCheckRun.resumeHint")}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                >
                  {resuming ? t("common.loading") : t("linkCheckRun.resume")}
                </button>
              )}
              {isActive && (
                <button
                  type="button"
                  onClick={onCancel}
                  disabled={cancelling}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {cancelling ? t("common.loading") : t("linkCheckRun.cancel")}
                </button>
              )}
            </div>
          </header>

          {/* crawl progress while running */}
          {run.check_crawl && isActive && (
            <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                {run.total_links > 0
                  ? t("linkCheckRun.crawling", {
                      done: run.crawled,
                      total: run.total_links,
                    })
                  : t("linkCheckRun.preparing")}
              </p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="h-full bg-blue-500 transition-[width] duration-300 dark:bg-blue-400"
                  style={{
                    width: `${run.total_links > 0 ? Math.round((run.crawled / run.total_links) * 100) : 5}%`,
                  }}
                />
              </div>
            </div>
          )}

          {/* summary counters */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Counter label={t("linkCheckRun.broken")} value={run.broken_count} accent="red" />
            <Counter label={t("linkCheckRun.omitted")} value={run.omitted_count} accent="amber" />
            <Counter label={t("linkCheckRun.hallucinated")} value={run.hallucinated_count} accent="violet" />
            <Counter label={t("linkCheckRun.ok")} value={run.ok_count} accent="green" />
          </div>

          {run.error && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {run.error}
            </p>
          )}

          {/* filter bar — shown once the run produced any rows */}
          {!isActive && producedRows(run) && (
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <select
                value={filterProblem}
                onChange={(e) => setFilterProblem(e.target.value as LinkProblem | "")}
                className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              >
                <option value="">{t("linkCheckRun.filterAllProblems")}</option>
                <option value="broken">{t("linkCheckRun.broken")}</option>
                <option value="omitted">{t("linkCheckRun.omitted")}</option>
                <option value="hallucinated">{t("linkCheckRun.hallucinated")}</option>
                {run.include_ok && (
                  <option value="ok">{t("linkCheckRun.ok")}</option>
                )}
              </select>
              {run.status_codes_present.length > 0 && (
                <select
                  value={filterStatus}
                  onChange={(e) =>
                    setFilterStatus(e.target.value ? Number(e.target.value) : "")
                  }
                  className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value="">{t("linkCheckRun.filterAllCodes")}</option>
                  {run.status_codes_present.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              )}
              <input
                type="text"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder={t("linkCheckRun.searchPlaceholder")}
                className="min-w-[12rem] flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              />
            </div>
          )}

          {/* violations */}
          {run.total_violations === 0 ? (
            !isActive &&
            (anyFilterActive(filterProblem, filterStatus, q) ? (
              <p className="mt-4 rounded-md bg-neutral-50 px-4 py-3 text-sm text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400">
                {t("linkCheckRun.noMatches")}
              </p>
            ) : (
              <p className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-900/40 dark:bg-green-950/30 dark:text-green-300">
                {t("linkCheckRun.noViolations")}
              </p>
            ))
          ) : (
            <>
              <div className="mt-3 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                    <tr>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colRow")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colColumn")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colProblem")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colLink")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colDetail")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                    {run.items.map((v, i) => (
                      <tr
                        key={`${v.row_id}:${v.column_id}:${v.problem}:${i}`}
                        className="align-top hover:bg-neutral-50 dark:hover:bg-neutral-900"
                      >
                        <td className="px-3 py-2 tabular-nums text-neutral-500">
                          #{v.row_position + 1}
                        </td>
                        <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                          {v.column_name}
                        </td>
                        <td className="px-3 py-2">
                          <ProblemBadge problem={v.problem} />
                        </td>
                        <td className="max-w-xs px-3 py-2">
                          <a
                            href={v.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="break-all text-blue-600 hover:underline dark:text-blue-400"
                          >
                            {v.link}
                          </a>
                        </td>
                        <td className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                          {detailText(t, v)}
                          <button
                            type="button"
                            onClick={() => setEditing(v)}
                            className="ml-2 text-blue-600 hover:underline dark:text-blue-400"
                          >
                            {t("linkCheckRun.fix")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={run.page}
                pageSize={run.page_size}
                total={run.total_violations}
                onPage={setPage}
              />
            </>
          )}
        </>
      )}

      {editing && (
        <CellEditorModal
          title={`${editing.column_name} · #${editing.row_position + 1}`}
          initialValue={cellValues.get(`${editing.row_id}:${editing.column_id}`) ?? ""}
          defaultMode={columnKind(editing.column_id) === "output" ? "preview" : "edit"}
          onClose={() => setEditing(null)}
          onSave={saveEdit}
        />
      )}
    </main>
  );
}

function ProblemBadge({ problem }: { problem: LinkProblem }) {
  const { t } = useT();
  const cls =
    problem === "broken"
      ? "bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-500/30"
      : problem === "omitted"
        ? "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25"
        : problem === "ok"
          ? "bg-green-50 text-green-700 ring-green-200 dark:bg-green-950/40 dark:text-green-300 dark:ring-green-500/30"
          : "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:ring-violet-500/30";
  const label =
    problem === "broken"
      ? t("linkCheckRun.broken")
      : problem === "omitted"
        ? t("linkCheckRun.omitted")
        : problem === "ok"
          ? t("linkCheckRun.ok")
          : t("linkCheckRun.hallucinated");
  return (
    <span
      className={
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset " +
        cls
      }
    >
      {label}
    </span>
  );
}

/** Localized Detail text from the stable detail_code + status_code. */
function detailText(
  t: ReturnType<typeof useT>["t"],
  v: LinkViolation,
): string {
  switch (v.detail_code) {
    case "expected_missing":
      return t("linkCheckDetail.expectedMissing");
    case "not_in_expected":
      return t("linkCheckDetail.notInExpected");
    case "http_error":
      return t("linkCheckDetail.httpError", { code: v.status_code ?? "?" });
    case "timeout":
      return t("linkCheckDetail.timeout");
    case "unreachable":
      return t("linkCheckDetail.unreachable");
    case "blocked":
      return t("linkCheckDetail.blocked");
    case "redirect":
      return t("linkCheckDetail.redirect", { code: v.status_code ?? "?" });
    case "ok":
      return t("linkCheckDetail.ok", { code: v.status_code ?? "?" });
    default:
      return v.detail_code ?? "";
  }
}

function producedRows(run: LinkCheckRunDetail): boolean {
  return (
    run.broken_count + run.omitted_count + run.hallucinated_count > 0 ||
    (run.include_ok && run.ok_count > 0)
  );
}

function anyFilterActive(
  problem: LinkProblem | "",
  status: number | "",
  q: string,
): boolean {
  return problem !== "" || status !== "" || q.trim().length > 0;
}

function Counter({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "red" | "amber" | "violet" | "green";
}) {
  const cls =
    accent === "red"
      ? "text-red-700 dark:text-red-400"
      : accent === "amber"
        ? "text-amber-700 dark:text-amber-300"
        : accent === "violet"
          ? "text-violet-700 dark:text-violet-400"
          : "text-green-700 dark:text-green-400";
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900">
      <p className="text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className={"mt-0.5 text-lg font-semibold tabular-nums " + cls}>{value}</p>
    </div>
  );
}
