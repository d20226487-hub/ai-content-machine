"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { listPublishJobs, type PublishJob } from "@/lib/publish";
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

  const refresh = useCallback(async () => {
    try {
      const [r, j] = await Promise.all([
        getBulkRun(id),
        listPublishJobs({ page, page_size: pageSize, run_id: id }),
      ]);
      setRun(r);
      setJobs(j.items);
      setJobsTotal(j.total);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("bulkRun.failedToLoad"));
    }
  }, [id, page, pageSize, t]);

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
      const next = await rerunFailedRows(id);
      router.push(`/publish/runs/${next.id}`);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("bulkRun.rerunFailedFailed"));
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
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("bulkRun.runHash", { id: run.id })}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            <b>{run.table_name ?? t("bulkRuns.tableFallback", { id: run.table_id })}</b> →{" "}
            <b>{run.domain_name ?? t("pubHistory.deletedDomain")}</b>
            {run.profile_name && <> · {run.profile_name}</>}
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

      {/* Per-row jobs */}
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("bulkRun.colTime")}</th>
              <th className="px-3 py-2">{t("bulkRun.colRow")}</th>
              <th className="px-3 py-2">{t("bulkRun.colStatus")}</th>
              <th className="px-3 py-2">{t("bulkRun.colPost")}</th>
              <th className="px-3 py-2">{t("bulkRun.colError")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {jobs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-neutral-500">
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
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[j.status] ?? STATUS_BADGE.queued}`}
                  >
                    {j.status}
                  </span>
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
    </main>
  );
}
