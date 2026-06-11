"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getLanguageSyncRun,
  resumeRun,
  retryFailedRun,
  type LanguageSyncResultRow,
  type LanguageSyncRunDetail,
} from "@/lib/publishLanguages";

/**
 * Detail page for one language-sync run.
 *
 * The sync runs in the background now, so this page polls while the run is
 * queued/running — driving a live progress bar and flipping each per-site
 * row from "pending" to its outcome as the worker reaches it. Once done it
 * stops polling and (if anything failed) offers a one-click Retry-failed,
 * which re-attempts just the failed sites in place and resumes polling.
 */
export default function LanguageSyncRunPage({
  params,
}: {
  // Next 15 typed route params come in as a Promise.
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const runId = Number(id);
  const { t } = useT();
  const [run, setRun] = useState<LanguageSyncRunDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "retry" | "resume">("");
  // Bumping this restarts the poll effect — used after retry/resume kicks a
  // finished run back into 'queued'.
  const [pollKey, setPollKey] = useState(0);
  // Whether the latest fetch saw an active run (drives "schedule next poll?").
  const activeRef = useRef(true);

  const tick = useCallback(async (): Promise<boolean> => {
    try {
      const r = await getLanguageSyncRun(runId);
      setRun(r);
      setLoadError(null);
      activeRef.current = r.status !== "done";
      return true;
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
      activeRef.current = false;
      return false;
    }
  }, [runId]);

  // Single poll loop: fetch immediately, then re-schedule every 2s only while
  // the run is still active. Re-runs (and thus restarts) when pollKey changes.
  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setLoadError("Invalid run id");
      return;
    }
    activeRef.current = true;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      const ok = await tick();
      if (cancelled || !ok) return;
      if (activeRef.current) timer = setTimeout(loop, 2000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId, tick, pollKey]);

  async function onRetry() {
    if (!run) return;
    setBusy("retry");
    try {
      await retryFailedRun(run.id);
      setPollKey((k) => k + 1);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function onResume() {
    if (!run) return;
    setBusy("resume");
    try {
      await resumeRun(run.id);
      setPollKey((k) => k + 1);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  const active = run?.status === "queued" || run?.status === "running";
  const processed = run
    ? run.results.filter((r) => r.state === "done").length
    : 0;
  const pct =
    run && run.total_count > 0
      ? Math.round((processed / run.total_count) * 100)
      : active
        ? 5
        : 0;

  return (
    <div className="space-y-4 p-5">
      <Link
        href="/publish/languages"
        className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
      >
        {t("langPage.runBack")}
      </Link>

      {loadError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {run && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {t("langPage.runTitle", { id: run.id })}
              </h1>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("langPage.runMeta", {
                  date: new Date(run.created_at).toLocaleString(),
                  by: run.created_by_name ?? "—",
                  source: run.source,
                })}
              </p>
              <p className="mt-1 font-mono text-xs text-neutral-600 dark:text-neutral-400">
                {t("langPage.runCounts", {
                  total: run.total_count,
                  ok: run.ok_count,
                  fail: run.fail_count,
                  skip: run.skip_count,
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <RunStatusBadge status={run.status} />
              {active && (
                <button
                  type="button"
                  onClick={onResume}
                  disabled={busy !== ""}
                  title={t("langPage.runResumeHint")}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                >
                  {busy === "resume" ? t("common.loading") : t("langPage.runResume")}
                </button>
              )}
              {run.status === "done" && run.fail_count > 0 && (
                <button
                  type="button"
                  onClick={onRetry}
                  disabled={busy !== ""}
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 dark:bg-blue-500"
                >
                  {busy === "retry"
                    ? t("common.loading")
                    : t("langPage.runRetryFailed", { n: run.fail_count })}
                </button>
              )}
            </div>
          </header>

          {/* live progress while the worker is processing */}
          {active && (
            <div className="rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                {t("langPage.runProgress", {
                  done: processed,
                  total: run.total_count,
                })}
              </p>
              <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="h-full bg-blue-500 transition-[width] duration-300 dark:bg-blue-400"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
            <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
              <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  <th className="px-3 py-2">{t("langPage.resultDomain")}</th>
                  <th className="px-3 py-2">{t("langPage.resultLanguages")}</th>
                  <th className="px-3 py-2">{t("langPage.resultStatus")}</th>
                  <th className="px-3 py-2">{t("langPage.resultElapsed")}</th>
                  <th className="px-3 py-2">{t("langPage.resultDetail")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {run.results.map((r) => (
                  <tr
                    key={r.id}
                    className="align-top hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                  >
                    <td className="px-3 py-2 font-mono text-xs">{r.domain_name}</td>
                    <td className="px-3 py-2 text-xs">
                      {r.languages.length > 0 ? (
                        <span className="font-mono">{r.languages.join(", ")}</span>
                      ) : (
                        <span className="text-neutral-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <StatusBadge r={r} />
                    </td>
                    <td className="px-3 py-2 text-xs tabular-nums text-neutral-600 dark:text-neutral-400">
                      {r.elapsed_ms != null ? `${r.elapsed_ms}ms` : "—"}
                    </td>
                    <td className="max-w-md px-3 py-2 text-xs">
                      {r.state === "pending" ? (
                        <span className="text-neutral-400">—</span>
                      ) : r.skipped ? (
                        <span className="text-neutral-500 dark:text-neutral-400">
                          {r.skip_reason ?? "—"}
                        </span>
                      ) : (
                        <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-neutral-600 dark:text-neutral-400">
                          {r.detail ?? "—"}
                        </pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const { t } = useT();
  if (status === "done") {
    return (
      <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-700 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600">
        {t("langPage.runStatusDone")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-inset ring-blue-600/20 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-400/30">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" />
      {status === "queued"
        ? t("langPage.runStatusQueued")
        : t("langPage.runStatusRunning")}
    </span>
  );
}

function StatusBadge({ r }: { r: LanguageSyncResultRow }) {
  const { t } = useT();
  if (r.state === "pending") {
    return (
      <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-600 ring-1 ring-inset ring-blue-600/20 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-400/30">
        {t("langPage.resultPending")}
      </span>
    );
  }
  if (r.skipped) {
    return (
      <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-700 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600">
        {t("langPage.resultSkipped")}
      </span>
    );
  }
  if (r.ok) {
    return (
      <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700 ring-1 ring-inset ring-green-600/20 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30">
        {t("langPage.resultOk")}
        {r.status_code != null ? ` · ${r.status_code}` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 ring-1 ring-inset ring-red-600/20 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30">
      {t("langPage.resultFail")}
      {r.status_code != null ? ` · ${r.status_code}` : ""}
    </span>
  );
}
