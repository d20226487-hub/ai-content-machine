"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { CellEditorModal } from "@/components/CellEditorModal";
import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { LinkFixModal, type FixTargetChoice } from "@/components/LinkFixModal";
import { Pagination } from "@/components/Pagination";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { TranslationTableView } from "@/components/TranslationTableView";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable, upsertCells } from "@/lib/library";
import {
  cancelLinkCheckRun,
  getLinkCheckRun,
  resumeLinkCheckRun,
  type LinkCheckRunDetail,
  type LinkProblem,
  type LinkResolution,
  type LinkTypeFilter,
  type LinkViolation,
} from "@/lib/linkCheck";
import {
  deleteLinkFixRun,
  listLinkFixRuns,
  renameLinkFixRun,
  startLinkFix,
  type LinkFixRun,
} from "@/lib/linkFix";
import { RunRowActions } from "@/components/RunRowActions";
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
  const router = useRouter();

  // Rows the user picked to fix with AI (persists across pages).
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [startingFix, setStartingFix] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);
  // Which fix was requested (rows scope). null = modal closed.
  const [fixScope, setFixScope] = useState<{ rowIds: number[] | null } | null>(null);
  // Correction runs launched from THIS check run (nested below).
  const [fixRuns, setFixRuns] = useState<LinkFixRun[]>([]);

  const [run, setRun] = useState<LinkCheckRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [columns, setColumns] = useState<BulkColumn[]>([]);
  const [cellValues, setCellValues] = useState<Map<string, string>>(new Map());
  const [editing, setEditing] = useState<LinkViolation | null>(null);
  const [filterProblem, setFilterProblem] = useState<LinkProblem | "">("");
  const [filterLinkType, setFilterLinkType] = useState<LinkTypeFilter | "">("");
  const [filterStatus, setFilterStatus] = useState<number | "">("");
  const [filterResolution, setFilterResolution] = useState<
    LinkResolution | "untouched" | ""
  >("");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [qNegate, setQNegate] = useState(false);
  const stoppedRef = useRef(false);

  // Debounce the link search so each keystroke doesn't refetch.
  useEffect(() => {
    const id = setTimeout(() => setQ(qInput), 350);
    return () => clearTimeout(id);
  }, [qInput]);

  // Any filter change resets to page 1.
  useEffect(() => {
    setPage(1);
  }, [filterProblem, filterLinkType, filterStatus, filterResolution, q, qNegate]);

  const tick = useCallback(
    async (p: number, isStale?: () => boolean) => {
      try {
        const r = await getLinkCheckRun(rid, p, PAGE_SIZE, {
          problem: filterProblem || undefined,
          link_type: filterLinkType || undefined,
          status_code: filterStatus === "" ? undefined : filterStatus,
          resolution: filterResolution || undefined,
          q: q || undefined,
          q_negate: qNegate,
        });
        // A page/filter change may have superseded this request while it was
        // in flight — don't let the late response clobber the newer state.
        if (isStale?.()) return;
        setRun(r);
        setError(null);
        if (r.status === "done" || r.status === "cancelled" || r.status === "failed") {
          stoppedRef.current = true;
        }
      } catch (e) {
        if (isStale?.()) return;
        setError(e instanceof ApiError ? e.message : String(e));
        stoppedRef.current = true;
      }
    },
    [rid, filterProblem, filterLinkType, filterStatus, filterResolution, q, qNegate],
  );

  // Poll while active; refetch immediately on page or filter change.
  useEffect(() => {
    if (!Number.isFinite(rid)) return;
    stoppedRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick(page, () => cancelled);
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

  // Load + poll the correction runs launched from this check run. Polling
  // stops once none are active (queued/running).
  useEffect(() => {
    if (!Number.isFinite(rid) || !Number.isFinite(tableId)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      try {
        const runs = await listLinkFixRuns(tableId, { sourceRunId: rid });
        if (!cancelled) setFixRuns(runs);
        const active = runs.some(
          (r) => r.status === "queued" || r.status === "running",
        );
        if (!cancelled && active) timer = setTimeout(loop, 3000);
      } catch {
        /* non-fatal */
      }
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [rid, tableId]);

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

  // Translation runs reuse the juxtapose machinery but the omitted/hallucinated
  // problems mean "missing localized link" / "wrong (non-localized) link" —
  // relabel them so the page reads in the tool's own terms.
  const isTranslation = !!run?.translation_config;
  const omittedLabel = t(
    isTranslation ? "linkCheckRun.tOmitted" : "linkCheckRun.omitted",
  );
  const hallucinatedLabel = t(
    isTranslation ? "linkCheckRun.tHallucinated" : "linkCheckRun.hallucinated",
  );

  // Mode shown in the run title so runs are self-describing.
  const modeLabel = !run
    ? ""
    : isTranslation
      ? t("linkCheckRun.translationMode")
      : [
          run.check_crawl && t("linkCheckRun.modeCrawl"),
          run.check_juxtapose && t("linkCheckRun.modeJuxtapose"),
        ]
          .filter(Boolean)
          .join(" + ");

  function toggleRow(rowId: number) {
    setSelectedRows((cur) => {
      const next = new Set(cur);
      if (next.has(rowId)) next.delete(rowId);
      else next.add(rowId);
      return next;
    });
  }

  async function startFix(
    rowIds: number[] | null,
    target: FixTargetChoice,
    prompt: string,
  ) {
    if (!run || startingFix) return;
    setStartingFix(true);
    setFixError(null);
    try {
      const fix = await startLinkFix(tableId, {
        source_run_id: run.id,
        row_ids: rowIds,
        // Only fix what the run page is currently showing.
        problem: filterProblem || null,
        status_code: filterStatus === "" ? null : filterStatus,
        q: q || null,
        q_negate: qNegate,
        // Where corrected output goes.
        target_column_id: target.kind === "existing" ? target.columnId : null,
        new_column_name: target.kind === "new" ? target.name : null,
        // Per-job correction prompt (defaulted from the previous job).
        prompt: prompt || null,
      });
      router.push(`/library/${tableId}/link-fix/runs/${fix.id}`);
    } catch (e) {
      setFixError(e instanceof ApiError ? e.message : String(e));
      setStartingFix(false);
      setFixScope(null);
    }
  }

  // Fixing needs the expected-links context (typo vs hallucination) and a
  // finished run with at least one fixable problem.
  const fixableCount =
    (run?.broken_count ?? 0) +
    (run?.omitted_count ?? 0) +
    (run?.hallucinated_count ?? 0);
  const canFix =
    !!run &&
    !isActive &&
    (run.expected_column_ids.length > 0 || isTranslation) &&
    fixableCount > 0;
  // Without expected columns there's nothing to fix typos against — surface
  // why the fix buttons aren't offered. Translation runs recompute expected
  // links server-side, so they're never blocked for this reason.
  const fixBlockedNoExpected =
    !!run &&
    !isActive &&
    run.expected_column_ids.length === 0 &&
    !isTranslation &&
    fixableCount > 0;
  // A filter is narrowing the shown violations — the fix only touches those.
  const filterActive =
    filterProblem !== "" ||
    filterStatus !== "" ||
    filterResolution !== "" ||
    q.trim().length > 0;

  // The in-place re-verify can stamp violations; show the Solved/Unsolved/
  // Untouched filter once any correction run exists for this check.
  const hasResolution = fixRuns.length > 0;

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("linkCheck.title"),
            href: `/library/${tableId}/link-check`,
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
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                  {modeLabel
                    ? t("linkCheckRun.titleWithMode", {
                        id: run.id,
                        mode: modeLabel,
                      })
                    : t("linkCheckRun.title", { id: run.id })}
                </h1>
                <LinkCheckStatusChip status={run.status} />
              </div>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("linkCheckRun.meta", {
                  by: run.created_by_name ?? "—",
                  when: new Date(run.created_at).toLocaleString(),
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {isTranslation && (
                <Link
                  href={`/library/${tableId}/link-check?rerun=${rid}`}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                >
                  {t("linkCheckRun.rerunWithChanges")}
                </Link>
              )}
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

          {/* summary counters — juxtapose contributes omitted/hallucinated;
              the crawl contributes the HTTP status-class breakdown (404 =
              "битые", plus whole 5xx / 3xx / 2xx classes). */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {run.check_juxtapose && (
              <>
                <Counter label={omittedLabel} value={run.omitted_count} accent="amber" />
                <Counter label={hallucinatedLabel} value={run.hallucinated_count} accent="violet" />
              </>
            )}
            {run.check_crawl && (
              <>
                <Counter label={t("linkCheckRun.broken")} value={run.status_404} accent="red" />
                <Counter label={t("linkCheckRun.status5xx")} value={run.status_5xx} accent="orange" />
                <Counter label={t("linkCheckRun.status3xx")} value={run.status_3xx} accent="sky" />
                <Counter label={t("linkCheckRun.status2xx")} value={run.status_2xx} accent="green" />
              </>
            )}
          </div>
          {run.check_crawl && (
            <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-300">
              {t("linkCheckRun.statusCountsHint")}
            </p>
          )}

          {isTranslation && (
            <div className="mt-3">
              <Link
                href={`/library/${tableId}/link-check/runs/${rid}/table`}
                className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                {t("linkCheckRun.viewRawTable")} →
              </Link>
            </div>
          )}

          {run.error && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {run.error}
            </p>
          )}

          {fixError && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {fixError}
            </p>
          )}

          {/* AI fix actions — only when the run finished with fixable problems
              and an expected-links column gave us the context to fix against.
              Translation runs fix per-selection from the overview's bulk bar
              instead, so this "Fix all" bar is hidden for them. */}
          {canFix && !isTranslation && (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-sm dark:border-violet-900/40 dark:bg-violet-950/20">
              <span className="text-violet-800 dark:text-violet-200">
                {selectedRows.size > 0
                  ? t("linkFix.selectedRows", { n: selectedRows.size })
                  : filterActive
                    ? t("linkFix.fixHintFiltered")
                    : t("linkFix.fixHint")}
              </span>
              <div className="ml-auto flex items-center gap-2">
                {selectedRows.size > 0 && (
                  <button
                    type="button"
                    onClick={() => setFixScope({ rowIds: Array.from(selectedRows) })}
                    disabled={startingFix}
                    className="rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-60"
                  >
                    {t("linkFix.fixSelected", { n: selectedRows.size })}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setFixScope({ rowIds: null })}
                  disabled={startingFix}
                  className="rounded-md border border-violet-300 px-3 py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-100 disabled:opacity-60 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-900/30"
                >
                  {filterActive ? t("linkFix.fixAllShown") : t("linkFix.fixAll")}
                </button>
              </div>
            </div>
          )}

          {fixBlockedNoExpected && (
            <p className="mt-4 rounded-md bg-neutral-50 px-3 py-2 text-xs text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400">
              {t("linkFix.needExpected")}
            </p>
          )}

          {/* Translation runs replace the materialized violations table with
              the raw translation-links table, filtered to just the problem
              links. Crawl/juxtapose runs keep the violations table below. */}
          {isTranslation && !isActive && (
            <div className="mt-5">
              <TranslationTableView
                runId={rid}
                discrepancyLinksOnly
                onFixRows={
                  canFix ? (rowIds) => setFixScope({ rowIds }) : undefined
                }
              />
            </div>
          )}

          {/* filter bar — shown once the run produced any rows */}
          {!isTranslation && !isActive && producedRows(run) && (
            <div className="mt-5 flex flex-wrap items-center gap-2">
              {/* The problem filter only makes sense when juxtapose ran — a
                  crawl-only (status-codes) run has just broken/ok, which the
                  status-code filter already covers. */}
              {run.check_juxtapose && (
                <select
                  value={filterProblem}
                  onChange={(e) => setFilterProblem(e.target.value as LinkProblem | "")}
                  className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value="">{t("linkCheckRun.filterAllProblems")}</option>
                  {!isTranslation && (
                    <option value="broken">{t("linkCheckRun.broken")}</option>
                  )}
                  <option value="omitted">{omittedLabel}</option>
                  <option value="hallucinated">{hallucinatedLabel}</option>
                  {run.include_ok && (
                    <option value="ok">{t("linkCheckRun.ok")}</option>
                  )}
                </select>
              )}
              {/* Link-type filter — only when the run classified links. */}
              {run.classify_config && (
                <select
                  value={filterLinkType}
                  onChange={(e) =>
                    setFilterLinkType(e.target.value as LinkTypeFilter | "")
                  }
                  className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value="">{t("linkCheckRun.rawTypeAll")}</option>
                  <option value="product">{t("linkCheckRun.rawTypeProduct")}</option>
                  <option value="internal">{t("linkCheckRun.rawTypeInternal")}</option>
                  <option value="external">{t("linkCheckRun.rawTypeExternal")}</option>
                </select>
              )}
              {hasResolution && (
                <select
                  value={filterResolution}
                  onChange={(e) =>
                    setFilterResolution(
                      e.target.value as LinkResolution | "untouched" | "",
                    )
                  }
                  className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value="">{t("linkCheckRun.filterAllResolutions")}</option>
                  <option value="solved">{t("linkCheckRun.resSolved")}</option>
                  <option value="unsolved">{t("linkCheckRun.resUnsolved")}</option>
                  <option value="untouched">{t("linkCheckRun.resUntouched")}</option>
                </select>
              )}
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
              <select
                value={qNegate ? "not" : "has"}
                onChange={(e) => setQNegate(e.target.value === "not")}
                className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              >
                <option value="has">{t("linkCheckRun.searchContains")}</option>
                <option value="not">{t("linkCheckRun.searchNotContains")}</option>
              </select>
              <input
                type="text"
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder={t("linkCheckRun.searchPlaceholder")}
                className="min-w-[10rem] flex-1 rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              />
            </div>
          )}

          {/* violations (crawl / juxtapose runs only) */}
          {!isTranslation &&
            (run.total_violations === 0 ? (
            !isActive &&
            (anyFilterActive(filterProblem, filterStatus, filterResolution, q) ? (
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
                      {canFix && <th className="w-8 px-3 py-2" />}
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colRow")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colColumn")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colProblem")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colLink")}</th>
                      <th className="px-3 py-2 font-medium">{t("linkCheckRun.colDetail")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                    {run.items.map((v, i) => {
                      const solved = v.resolution === "solved";
                      return (
                      <tr
                        key={`${v.row_id}:${v.column_id}:${v.problem}:${i}`}
                        className={
                          "align-top hover:bg-neutral-50 dark:hover:bg-neutral-900 " +
                          (solved
                            ? "opacity-50 [&_td]:line-through [&_td_button]:no-underline"
                            : "")
                        }
                      >
                        {canFix && (
                          <td className="px-3 py-2 [&]:no-underline">
                            {v.problem !== "ok" && !solved && (
                              <input
                                type="checkbox"
                                checked={selectedRows.has(v.row_id)}
                                onChange={() => toggleRow(v.row_id)}
                                title={t("linkFix.selectRowHint")}
                                className="h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
                              />
                            )}
                          </td>
                        )}
                        <td className="px-3 py-2 tabular-nums text-neutral-500">
                          #{v.row_position + 1}
                        </td>
                        <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                          {v.column_name}
                        </td>
                        <td className="px-3 py-2">
                          <span className="inline-flex items-center gap-1.5">
                            <ProblemBadge v={v} isTranslation={isTranslation} />
                            {solved && (
                              <span
                                className="text-green-600 no-underline dark:text-green-400"
                                title={t("linkFix.fixedBadge")}
                              >
                                ✓
                              </span>
                            )}
                          </span>
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
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={run.total_violations}
                onPage={setPage}
              />
            </>
            ))}

          {/* Correction runs launched from this check run (kept at the
              bottom, below the violations). */}
          {fixRuns.length > 0 && (
            <section className="mt-8">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t("linkFix.correctionsHeading")}
              </h2>
              <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
                {fixRuns.map((fr) => (
                  <li key={fr.id}>
                    <Link
                      href={`/library/${tableId}/link-fix/runs/${fr.id}`}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                    >
                      <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-300">
                        {fr.name || t("linkFix.runLabel", { id: fr.id })}
                        <span className="ml-2 text-xs text-neutral-400">
                          {new Date(fr.created_at).toLocaleString()}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2 text-xs">
                        {fr.reverted_at && (
                          <span className="text-amber-600 dark:text-amber-400">
                            {t("linkFixRun.revertedBadge")}
                          </span>
                        )}
                        <span className="text-neutral-500 dark:text-neutral-400">
                          {fr.done}/{fr.total}
                        </span>
                        <LinkCheckStatusChip status={fr.status} />
                        <RunRowActions
                          name={fr.name}
                          canDelete={
                            fr.status !== "queued" && fr.status !== "running"
                          }
                          onRename={async (n) => {
                            await renameLinkFixRun(fr.id, n);
                            setFixRuns(
                              await listLinkFixRuns(tableId, { sourceRunId: rid }),
                            );
                          }}
                          onDelete={async () => {
                            await deleteLinkFixRun(fr.id);
                            setFixRuns(
                              await listLinkFixRuns(tableId, { sourceRunId: rid }),
                            );
                          }}
                        />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {fixScope && (
        <LinkFixModal
          tableId={tableId}
          columns={columns}
          count={
            fixScope.rowIds ? fixScope.rowIds.length : (run?.total_violations ?? 0)
          }
          busy={startingFix}
          onClose={() => setFixScope(null)}
          onConfirm={(target, prompt) =>
            void startFix(fixScope.rowIds, target, prompt)
          }
        />
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

const BADGE_RED =
  "bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-500/30";
const BADGE_AMBER =
  "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25";
const BADGE_VIOLET =
  "bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:ring-violet-500/30";
const BADGE_GREEN =
  "bg-green-50 text-green-700 ring-green-200 dark:bg-green-950/40 dark:text-green-300 dark:ring-green-500/30";
const BADGE_ORANGE =
  "bg-orange-50 text-orange-700 ring-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:ring-orange-500/30";
const BADGE_SKY =
  "bg-sky-50 text-sky-700 ring-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:ring-sky-500/30";

/** Badge for one violation. Juxtapose problems keep their semantic label;
 * crawl problems (broken/ok) are classified by HTTP status — only a 404 is
 * "битые", with whole 5xx / 3xx / 2xx classes otherwise. */
function ProblemBadge({
  v,
  isTranslation,
}: {
  v: LinkViolation;
  isTranslation?: boolean;
}) {
  const { t } = useT();
  let label: string;
  let cls: string;
  if (v.problem === "omitted") {
    label = t(isTranslation ? "linkCheckRun.tOmitted" : "linkCheckRun.omitted");
    cls = BADGE_AMBER;
  } else if (v.problem === "hallucinated") {
    label = t(
      isTranslation ? "linkCheckRun.tHallucinated" : "linkCheckRun.hallucinated",
    );
    cls = BADGE_VIOLET;
  } else {
    // crawl-origin: broken | ok → classify by status code.
    const sc = v.status_code;
    if (sc === 404) {
      label = t("linkCheckRun.broken");
      cls = BADGE_RED;
    } else if (sc != null && sc >= 500 && sc <= 599) {
      label = t("linkCheckRun.status5xx");
      cls = BADGE_ORANGE;
    } else if (sc != null && sc >= 300 && sc <= 399) {
      label = t("linkCheckRun.status3xx");
      cls = BADGE_SKY;
    } else if (sc != null && sc >= 200 && sc <= 299) {
      label = t("linkCheckRun.status2xx");
      cls = BADGE_GREEN;
    } else if (sc != null) {
      // Other 4xx (403/410/…): a real problem, but not "битые".
      label = `HTTP ${sc}`;
      cls = BADGE_RED;
    } else if (v.problem === "ok") {
      label = t("linkCheckRun.ok");
      cls = BADGE_GREEN;
    } else {
      // No status code — a network failure (timeout / unreachable / blocked).
      label = t("linkCheckRun.errorBadge");
      cls = BADGE_RED;
    }
  }
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
  resolution: LinkResolution | "untouched" | "",
  q: string,
): boolean {
  return (
    problem !== "" || status !== "" || resolution !== "" || q.trim().length > 0
  );
}

function Counter({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "red" | "amber" | "violet" | "green" | "orange" | "sky";
}) {
  const cls =
    accent === "red"
      ? "text-red-700 dark:text-red-400"
      : accent === "amber"
        ? "text-amber-700 dark:text-amber-300"
        : accent === "violet"
          ? "text-violet-700 dark:text-violet-400"
          : accent === "orange"
            ? "text-orange-700 dark:text-orange-400"
            : accent === "sky"
              ? "text-sky-700 dark:text-sky-400"
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
