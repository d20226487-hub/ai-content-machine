"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  listBulkRuns,
  type BulkRunStatus,
  type BulkRunSummary,
} from "@/lib/publishBulk";

const STATUS_BADGE: Record<BulkRunStatus, string> = {
  done: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  running: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  paused: "bg-amber-50 text-amber-800 ring-amber-600/10 dark:bg-amber-950/40 dark:text-amber-400 dark:ring-amber-400/30",
  cancelled: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
  queued: "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30",
};

export default function RunsPage() {
  const { t } = useT();
  const [runs, setRuns] = useState<BulkRunSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const r = await listBulkRuns({ page_size: 100 });
        if (!cancelled) setRuns(r.items);
      } catch (err) {
        if (!cancelled)
          setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
      }
    }
    tick();
    const handle = setInterval(() => {
      if (!runs) return;
      const inFlight = runs.some(
        (r) => r.status === "running" || r.status === "queued" || r.status === "paused",
      );
      if (inFlight) tick();
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs?.map((r) => `${r.id}:${r.status}:${r.done}:${r.failed}`).join(",")]);

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("bulkRuns.title")}
        </h1>
        <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
          {t("bulkRuns.subtitle")}
        </p>
      </div>

      {loadError && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("bulkRuns.colStarted")}</th>
              <th className="px-3 py-2">{t("bulkRuns.colTable")}</th>
              <th className="px-3 py-2">{t("bulkRuns.colDomain")}</th>
              <th className="px-3 py-2">{t("bulkRuns.colProfile")}</th>
              <th className="px-3 py-2">{t("bulkRuns.colStatus")}</th>
              <th className="px-3 py-2">{t("bulkRuns.colProgress")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {runs === null && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-neutral-500">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {runs !== null && runs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-neutral-500">
                  {t("bulkRuns.empty")}
                </td>
              </tr>
            )}
            {runs?.map((r) => {
              const total = Math.max(1, r.total);
              const pct = Math.round((100 * (r.done + r.failed + r.skipped)) / total);
              return (
                <tr
                  key={r.id}
                  className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                  onClick={() => (window.location.href = `/publish/runs/${r.id}`)}
                >
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/publish/runs/${r.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium text-neutral-900 hover:underline dark:text-neutral-100"
                    >
                      {r.table_name ?? t("bulkRuns.tableFallback", { id: r.table_id })}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                    {r.domain_name ?? t("pubHistory.deletedDomain")}
                  </td>
                  <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                    {r.profile_name ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[r.status] ?? STATUS_BADGE.queued}`}
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-32 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
                        <div
                          className="h-full bg-green-500 transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-neutral-700 dark:text-neutral-300">
                        {r.done + r.failed + r.skipped}/{r.total}
                        {r.failed > 0 && (
                          <span className="ml-1 text-red-600 dark:text-red-400">
                            {t("bulkRuns.failedSuffix", { count: r.failed })}
                          </span>
                        )}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </main>
  );
}
