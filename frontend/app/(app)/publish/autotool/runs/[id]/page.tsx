"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelAutotoolRun,
  getAutotoolRun,
  retryFailedAutotoolRun,
  type AutotoolRunDetail,
} from "@/lib/autotool";

const STATUS_BADGE: Record<string, string> = {
  done: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  running: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  sending: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  cancelled: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
  skipped: "bg-neutral-100 text-neutral-600 ring-neutral-500/10 dark:bg-neutral-800 dark:text-neutral-400 dark:ring-neutral-500/30",
  queued: "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30",
  sent: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
};

export default function AutotoolRunDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const id = Number(params.id);

  const [run, setRun] = useState<AutotoolRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setRun(await getAutotoolRun(id, page, pageSize));
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    }
  }, [id, page, pageSize, t]);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    refresh();
  }, [id, refresh]);

  useEffect(() => {
    if (!run) return;
    if (!["queued", "running"].includes(run.status)) return;
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
      <main className="mx-auto max-w-6xl px-5 py-6">
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      </main>
    );
  }
  if (!run) {
    return (
      <main className="mx-auto max-w-6xl px-5 py-6 text-sm text-neutral-500">
        {t("common.loading")}
      </main>
    );
  }

  const total = Math.max(1, run.total);
  const processed = run.sent + run.failed + run.skipped;
  const pct = Math.round((100 * processed) / total);
  const canCancel = ["queued", "running"].includes(run.status);
  const isTerminal = ["done", "failed", "cancelled"].includes(run.status);
  const canRetry = isTerminal && run.failed > 0;

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <button
        onClick={() => router.push("/publish/autotool/runs")}
        className="mb-3 text-xs text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
      >
        {t("autotoolRun.back")}
      </button>

      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("autotoolRun.runHash", { id: run.id })}
            <span
              className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[run.status] ?? STATUS_BADGE.queued}`}
            >
              {run.status}
            </span>
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            <b>{run.table_name || t("autotoolRun.tableFallback", { id: run.table_id ?? 0 })}</b>
            {" · "}
            {t("autotoolRun.pageSizeLabel", { size: run.page_size })}
            {" · "}
            <span className="break-all">{run.target_url}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canCancel && (
            <button
              onClick={() => action(cancelAutotoolRun)}
              disabled={busy}
              className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800/60 dark:text-red-400 dark:hover:bg-red-950/40"
            >
              {t("common.cancel")}
            </button>
          )}
          {canRetry && (
            <button
              onClick={() => action(retryFailedAutotoolRun)}
              disabled={busy}
              title={t("autotoolRun.retryFailedHint", { count: run.failed })}
              className="rounded-md border border-neutral-900 bg-neutral-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {t("autotoolRun.retryFailed", { count: run.failed })}
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mb-2 flex items-center justify-between text-xs text-neutral-700 dark:text-neutral-300">
          <span>{t("autotoolRun.processed", { done: processed, total: run.total })}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
          <div className="h-full bg-green-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500 dark:text-neutral-400">
          <span>{t("autotoolRun.sentPrefix", { count: run.sent })}</span>
          {run.failed > 0 && (
            <span className="text-red-600 dark:text-red-400">
              {t("autotoolRun.failedPrefix", { count: run.failed })}
            </span>
          )}
          {run.skipped > 0 && <span>{t("autotoolRun.skippedPrefix", { count: run.skipped })}</span>}
        </div>
      </div>

      {/* Items */}
      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("autotoolRun.colSite")}</th>
              <th className="px-3 py-2">{t("autotoolRun.colId")}</th>
              <th className="px-3 py-2">{t("autotoolRun.colPage")}</th>
              <th className="px-3 py-2">{t("autotoolRun.colStatus")}</th>
              <th className="px-3 py-2">{t("autotoolRun.colDetail")}</th>
              <th className="px-3 py-2">{t("autotoolRun.colTime")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {run.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-neutral-500">
                  {t("autotoolRun.empty")}
                </td>
              </tr>
            )}
            {run.items.map((it) => (
              <tr key={it.id}>
                <td className="px-3 py-2 font-mono text-xs text-neutral-700 dark:text-neutral-300 break-all">
                  {it.site}
                </td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-neutral-600 dark:text-neutral-400">
                  {it.external_id != null ? String(it.external_id) : "—"}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                  {t("autotoolCfg.pageRange", {
                    from: it.start + 1,
                    to: Math.min(it.start + run.page_size, it.total),
                    total: it.total,
                  })}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[it.status] ?? STATUS_BADGE.queued}`}
                  >
                    {it.status}
                  </span>
                  {it.status_code != null && (
                    <span className="ml-1 inline-flex items-center rounded bg-neutral-100 px-1 py-0.5 font-mono text-[10px] font-medium text-neutral-600 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-400 dark:ring-neutral-700">
                      {it.status_code}
                    </span>
                  )}
                </td>
                <td
                  className="max-w-md truncate px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400"
                  title={it.response_snippet ?? it.detail ?? undefined}
                >
                  {it.detail ?? "—"}
                  {it.elapsed_ms != null && (
                    <span className="ml-1 text-neutral-400 dark:text-neutral-500">· {it.elapsed_ms}ms</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                  {new Date(it.created_at).toLocaleTimeString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      {run.items_total > pageSize && (
        <div className="mt-3 flex items-center justify-between gap-3 text-xs text-neutral-600 dark:text-neutral-400">
          <span>
            {t("common.showingRange", {
              from: (page - 1) * pageSize + 1,
              to: Math.min(page * pageSize, run.items_total),
              total: run.items_total,
            })}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.prev")}
            </button>
            <span>
              {t("common.pageXslashY", {
                page,
                total: Math.max(1, Math.ceil(run.items_total / pageSize)),
              })}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * pageSize >= run.items_total}
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
