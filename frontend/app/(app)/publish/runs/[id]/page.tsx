"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { Modal } from "@/components/Modal";
import {
  getPublishJob,
  listPublishJobs,
  type JobStatus,
  type PublishJob,
  type PublishJobDetail,
} from "@/lib/publish";
import {
  cancelBulkRun,
  getBulkRun,
  pauseBulkRun,
  rerunFailedRows,
  resumeBulkRun,
  type BulkRunDetail,
} from "@/lib/publishBulk";

const STATUS_BADGE: Record<string, string> = {
  done: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  running: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  posting: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  paused: "bg-amber-50 text-amber-800 ring-amber-600/10 dark:bg-amber-950/40 dark:text-amber-400 dark:ring-amber-400/30",
  cancelled: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
  queued: "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30",
  posted: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  skipped: "bg-neutral-100 text-neutral-600 ring-neutral-500/10 dark:bg-neutral-800 dark:text-neutral-400 dark:ring-neutral-500/30",
};

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const id = Number(params.id);

  const [run, setRun] = useState<BulkRunDetail | null>(null);
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Multi-mode filters: by domain id (null = "(unresolved)") and by job status.
  const [filterDomain, setFilterDomain] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<"all" | JobStatus>("all");

  // Per-row "view request (curl)" modal — fetched on demand from the job
  // detail endpoint so the heavy payload isn't pulled for every list row.
  const [reqJob, setReqJob] = useState<PublishJobDetail | null>(null);
  const [reqJobId, setReqJobId] = useState<number | null>(null);
  const [reqError, setReqError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function openRequest(jobId: number) {
    setReqJobId(jobId);
    setReqJob(null);
    setReqError(null);
    try {
      setReqJob(await getPublishJob(jobId));
    } catch (err) {
      setReqError(err instanceof ApiError ? err.message : String(err));
    }
  }

  const refresh = useCallback(async () => {
    try {
      const opts: Parameters<typeof listPublishJobs>[0] = {
        page,
        page_size: pageSize,
        run_id: id,
      };
      if (filterStatus !== "all") opts.status = filterStatus;
      if (filterDomain !== "all" && filterDomain !== "unresolved") {
        opts.domain_id = Number(filterDomain);
      }
      const [r, j] = await Promise.all([getBulkRun(id), listPublishJobs(opts)]);
      // For "unresolved" we still fetched all jobs, then filter client-side
      // since the listPublishJobs API doesn't support "domain_id IS NULL".
      let items = j.items;
      if (filterDomain === "unresolved") {
        items = items.filter((it) => it.domain_id == null);
      }
      setRun(r);
      setJobs(items);
      setJobsTotal(j.total);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("bulkRun.failedToLoad"));
    }
  }, [id, page, pageSize, filterDomain, filterStatus, t]);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    refresh();
  }, [id, refresh]);

  useEffect(() => {
    if (!run) return;
    const inFlight = ["running", "queued", "paused"].includes(run.status);
    if (!inFlight) return;
    const handle = setInterval(refresh, 2000);
    return () => clearInterval(handle);
  }, [run, refresh]);

  async function action(fn: (id: number) => Promise<unknown>) {
    setBusy(true);
    try {
      await fn(id);
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  const isMulti = run?.mode === "multi";

  if (loadError) {
    return (
      <main className="mx-auto max-w-7xl px-5 py-6">
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      </main>
    );
  }

  if (!run) {
    return (
      <main className="mx-auto max-w-7xl px-5 py-6 text-sm text-neutral-500">
        {t("common.loading")}
      </main>
    );
  }

  const total = Math.max(1, run.total);
  const pct = Math.round((100 * (run.done + run.failed + run.skipped)) / total);

  const canPause = run.status === "running" || run.status === "queued";
  const canResume = run.status === "paused";
  const canCancel = ["running", "queued", "paused"].includes(run.status);
  const isTerminal = ["done", "failed", "cancelled"].includes(run.status);
  const canRerunFailed = isTerminal && run.failed > 0;

  async function onRerunFailed() {
    setBusy(true);
    try {
      await rerunFailedRows(id);
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("bulkRun.rerunFailedFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <button
        onClick={() => router.push("/publish/runs")}
        className="mb-3 text-xs text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
      >
        {t("bulkRun.back")}
      </button>

      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("bulkRun.runHash", { id: run.id })}
            <span
              className={
                "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide " +
                (isMulti
                  ? "bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300"
                  : "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300")
              }
            >
              {isMulti ? t("bulkRun.modeMulti") : t("bulkRun.modeSingle")}
            </span>
            {run.operation === "update" && (
              <span
                className="inline-flex items-center rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                title={t("bulkRun.opUpdateHint", { kind: run.lookup_kind ?? "" })}
              >
                {t("bulkRun.opUpdate")}
              </span>
            )}
            {run.language_column_id != null && (
              <span
                className="inline-flex items-center rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-800 dark:bg-sky-950/40 dark:text-sky-300"
                title={t("bulkRun.perRowLangHint")}
              >
                {t("bulkRun.perRowLang")}
              </span>
            )}
            {run.on_slug_conflict === "skip" && (
              <span
                className="inline-flex items-center rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                title={t("bulkRun.onSlugSkipHint")}
              >
                {t("bulkRun.onSlugSkip")}
              </span>
            )}
            {run.on_slug_conflict === "update" && (
              <span
                className="inline-flex items-center rounded bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-violet-800 dark:bg-violet-950/40 dark:text-violet-300"
                title={t("bulkRun.onSlugUpsertHint")}
              >
                {t("bulkRun.onSlugUpsert")}
              </span>
            )}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            <b>{run.table_name ?? t("bulkRuns.tableFallback", { id: run.table_id })}</b>
            {!isMulti && (
              <>
                {" → "}
                <b>{run.domain_name ?? t("pubHistory.deletedDomain")}</b>
                {run.profile_name && <> · {run.profile_name}</>}
              </>
            )}
            {isMulti && (
              <> · {t("bulkRun.acrossDomains", { count: run.by_domain.length })}</>
            )}
            {run.language && <> · {run.language}</>}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[run.status] ?? STATUS_BADGE.queued}`}
          >
            {run.status}
          </span>
          {canPause && (
            <button
              onClick={() => action(pauseBulkRun)}
              disabled={busy}
              className="rounded-md border border-neutral-300 px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("bulkRun.pause")}
            </button>
          )}
          {canResume && (
            <button
              onClick={() => action(resumeBulkRun)}
              disabled={busy}
              className="rounded-md border border-neutral-300 px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("bulkRun.resume")}
            </button>
          )}
          {canCancel && (
            <button
              onClick={() => action(cancelBulkRun)}
              disabled={busy}
              className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800/60 dark:text-red-400 dark:hover:bg-red-950/40"
            >
              {t("common.cancel")}
            </button>
          )}
          {canRerunFailed && (
            <button
              onClick={onRerunFailed}
              disabled={busy}
              title={t("bulkRun.rerunFailedHint", { count: run.failed })}
              className="rounded-md border border-neutral-900 bg-neutral-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {t("bulkRun.rerunFailed", { count: run.failed })}
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mb-2 flex items-center justify-between text-xs text-neutral-700 dark:text-neutral-300">
          <span>
            {t("bulkRun.processed", { done: run.done + run.failed + run.skipped, total: run.total })}
          </span>
          <span>{pct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
          <div
            className="h-full bg-green-500 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500 dark:text-neutral-400">
          <span>{t("bulkRun.donePrefix", { count: run.done })}</span>
          {run.failed > 0 && (
            <span className="text-red-600 dark:text-red-400">
              {t("bulkRun.failedPrefix", { count: run.failed })}
            </span>
          )}
          {run.skipped > 0 && <span>{t("bulkRun.skippedPrefix", { count: run.skipped })}</span>}
        </div>
      </div>

      {/* Per-domain summary — multi mode only */}
      {isMulti && run.by_domain.length > 0 && (
        <div className="mb-4 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
          <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            {t("bulkRun.byDomainHeading", { count: run.by_domain.length })}
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="text-left text-[11px] font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                <tr>
                  <th className="py-1 pr-3">{t("bulkRun.colDomain")}</th>
                  <th className="py-1 pr-3 text-right">{t("bulkRun.colTotal")}</th>
                  <th className="py-1 pr-3 text-right">{t("bulkRun.colPosted")}</th>
                  <th className="py-1 pr-3 text-right">{t("bulkRun.colFailed")}</th>
                  <th className="py-1"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {run.by_domain.map((d, i) => {
                  const filterValue = d.domain_id == null ? "unresolved" : String(d.domain_id);
                  const isAllFailed = d.posted === 0 && d.failed > 0;
                  return (
                    <tr key={`${d.domain_id ?? "u"}-${i}`}>
                      <td className="py-1 pr-3 font-mono text-neutral-700 dark:text-neutral-300">
                        {d.domain_name ?? t("bulkRun.unresolved")}
                      </td>
                      <td className="py-1 pr-3 text-right tabular-nums">{d.total}</td>
                      <td className="py-1 pr-3 text-right tabular-nums text-green-700 dark:text-green-400">
                        {d.posted}
                      </td>
                      <td
                        className={
                          "py-1 pr-3 text-right tabular-nums " +
                          (d.failed > 0
                            ? "text-red-700 dark:text-red-400"
                            : "text-neutral-500 dark:text-neutral-400")
                        }
                      >
                        {d.failed}
                        {isAllFailed && (
                          <span
                            title={t("bulkRun.allFailedHint")}
                            className="ml-1 inline-block rounded bg-red-100 px-1 text-[10px] font-medium text-red-800 dark:bg-red-950/60 dark:text-red-300"
                          >
                            {t("bulkRun.allFailed")}
                          </span>
                        )}
                      </td>
                      <td className="py-1 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            setFilterDomain(filterValue);
                            setPage(1);
                          }}
                          className="text-[11px] text-blue-600 hover:underline dark:text-blue-400"
                        >
                          {t("bulkRun.filter")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Filters: domain + status — only useful in multi mode for domain;
          status filter helpful in both. */}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-neutral-600 dark:text-neutral-400">
        {isMulti && (
          <label className="flex items-center gap-1">
            <span>{t("bulkRun.filterDomain")}:</span>
            <select
              value={filterDomain}
              onChange={(e) => {
                setFilterDomain(e.target.value);
                setPage(1);
              }}
              className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
            >
              <option value="all">{t("bulkRun.filterAll")}</option>
              {run.by_domain.map((d, i) => (
                <option
                  key={`${d.domain_id ?? "u"}-${i}`}
                  value={d.domain_id == null ? "unresolved" : String(d.domain_id)}
                >
                  {d.domain_name ?? t("bulkRun.unresolved")} ({d.total})
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="flex items-center gap-1">
          <span>{t("bulkRun.filterStatus")}:</span>
          <select
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value as "all" | JobStatus);
              setPage(1);
            }}
            className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
          >
            <option value="all">{t("bulkRun.filterAll")}</option>
            <option value="posted">posted</option>
            <option value="failed">failed</option>
            <option value="posting">posting</option>
            <option value="queued">queued</option>
          </select>
        </label>
        {(filterDomain !== "all" || filterStatus !== "all") && (
          <button
            type="button"
            onClick={() => {
              setFilterDomain("all");
              setFilterStatus("all");
              setPage(1);
            }}
            className="text-blue-600 hover:underline dark:text-blue-400"
          >
            {t("bulkRun.clearFilters")}
          </button>
        )}
      </div>

      {/* Per-row jobs */}
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("bulkRun.colTime")}</th>
              <th className="px-3 py-2">{t("bulkRun.colRow")}</th>
              <th className="px-3 py-2">{t("bulkRun.colSlug")}</th>
              <th className="px-3 py-2">{t("bulkRun.colDomain")}</th>
              <th className="px-3 py-2">{t("bulkRun.colProfile")}</th>
              <th className="px-3 py-2">{t("bulkRun.colLang")}</th>
              <th className="px-3 py-2">{t("bulkRun.colStatus")}</th>
              <th className="px-3 py-2">{t("bulkRun.colPost")}</th>
              <th className="px-3 py-2">{t("bulkRun.colError")}</th>
              <th className="px-3 py-2">{t("bulkRun.colRequest")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {jobs.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-6 text-center text-neutral-500">
                  {t("bulkRun.empty")}
                </td>
              </tr>
            )}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                  {new Date(j.created_at).toLocaleTimeString()}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                  {(j.source_ref?.row_id as number | undefined) ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                  {j.slug ? (
                    j.slug
                  ) : (
                    <span className="italic text-amber-700 dark:text-amber-400">
                      {t("bulkRun.slugEmpty")}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs font-mono text-neutral-700 dark:text-neutral-300">
                  {j.domain_name ?? (j.domain_id == null ? <span className="text-neutral-500 italic">{t("bulkRun.unresolved")}</span> : j.domain_id)}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                  {j.profile_name ?? <span className="text-neutral-500">—</span>}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                  {j.language ?? <span className="text-neutral-500">—</span>}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[j.status] ?? STATUS_BADGE.queued}`}
                  >
                    {j.status}
                  </span>
                  {/* Upstream HTTP code (migration 0026). Rendered as a
                      small neutral chip next to the status badge so the
                      color signal stays single-sourced from the status
                      itself. Hidden for rows where the code is null
                      (legacy rows pre-migration, or queued/posting
                      rows that haven't hit the wire yet). */}
                  {j.status_code != null && (
                    <span
                      className="ml-1 inline-flex items-center rounded bg-neutral-100 px-1 py-0.5 font-mono text-[10px] font-medium text-neutral-600 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-400 dark:ring-neutral-700"
                      title={t("bulkRun.httpCodeTip")}
                    >
                      {j.status_code}
                    </span>
                  )}
                  {j.warnings && j.warnings.length > 0 && (
                    <span className="ml-1 inline-flex items-center rounded bg-amber-50 px-1 py-0.5 text-[10px] font-medium ring-1 ring-amber-600/10 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-400/30">
                      ⚠ {j.warnings.length}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs">
                  {j.cms_post_url ? (
                    <a
                      href={j.cms_post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline text-neutral-700 dark:text-neutral-300"
                    >
                      {t("bulkRun.viewLink")}
                    </a>
                  ) : (
                    <span className="text-neutral-500">—</span>
                  )}
                  {j.cms_post_id && (
                    <span className="ml-2 text-neutral-500 dark:text-neutral-400">
                      #{j.cms_post_id}
                    </span>
                  )}
                </td>
                <td className="max-w-md truncate px-3 py-2 text-xs" title={j.error ?? j.warnings?.join("\n") ?? undefined}>
                  {j.error && (
                    <span className="text-red-700 dark:text-red-400">{j.error}</span>
                  )}
                  {!j.error && j.warnings && j.warnings.length > 0 && (
                    <span className="text-amber-800 dark:text-amber-300">
                      {j.warnings[0]}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs">
                  <button
                    type="button"
                    onClick={() => openRequest(j.id)}
                    className="rounded-md border border-neutral-300 px-2 py-0.5 font-mono text-[11px] font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                  >
                    {t("bulkRun.viewRequest")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      {jobsTotal > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-600 dark:text-neutral-400">
          <span>
            {t("common.showingRange", {
              from: (page - 1) * pageSize + 1,
              to: Math.min(page * pageSize, jobsTotal),
              total: jobsTotal,
            })}
          </span>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1">
              <span>{t("common.rows")}</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPage(1);
                  setPageSize(Number(e.target.value));
                }}
                className="rounded-md border border-neutral-300 bg-white px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
              >
                {[25, 50, 100, 200].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.prev")}
            </button>
            <span>{t("common.pageXslashY", { page, total: Math.max(1, Math.ceil(jobsTotal / pageSize)) })}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * pageSize >= jobsTotal}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.nextArrow")}
            </button>
          </div>
        </div>
      )}

      {reqJobId != null && (
        <Modal
          size="max-w-3xl"
          onClose={() => {
            setReqJobId(null);
            setReqJob(null);
            setReqError(null);
            setCopied(false);
          }}
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {t("bulkRun.requestTitle", { id: reqJobId })}
              </h2>
              {reqJob?.curl_preview && (
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard?.writeText(reqJob.curl_preview ?? "");
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {copied ? t("common.copied") : t("bulkRun.copyCurl")}
                </button>
              )}
            </div>

            {reqError && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
                {reqError}
              </p>
            )}
            {!reqJob && !reqError && (
              <p className="text-xs text-neutral-500">{t("common.loading")}</p>
            )}
            {reqJob && (
              <>
                {reqJob.curl_preview ? (
                  <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap break-all rounded-md bg-neutral-950 p-3 text-[11px] leading-relaxed text-neutral-100">
                    {reqJob.curl_preview}
                  </pre>
                ) : (
                  <p className="rounded-md bg-neutral-50 px-3 py-2 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
                    {t("bulkRun.requestNone")}
                  </p>
                )}
                {reqJob.status_code != null && (
                  <p className="text-xs text-neutral-600 dark:text-neutral-400">
                    {t("bulkRun.responseStatus", { code: reqJob.status_code })}
                  </p>
                )}
                {reqJob.response_json && (
                  <div>
                    <p className="mb-1 text-xs font-medium text-neutral-700 dark:text-neutral-300">
                      {t("bulkRun.responseBody")}
                    </p>
                    <pre className="max-h-[30vh] overflow-auto whitespace-pre-wrap break-all rounded-md bg-neutral-100 p-3 text-[11px] text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200">
                      {JSON.stringify(reqJob.response_json, null, 2)}
                    </pre>
                  </div>
                )}
                {reqJob.error && (
                  <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
                    {reqJob.error}
                  </p>
                )}
              </>
            )}
          </div>
        </Modal>
      )}
    </main>
  );
}
