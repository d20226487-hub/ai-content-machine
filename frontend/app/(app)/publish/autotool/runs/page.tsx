"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { ApiError } from "@/lib/api";
import { Pagination } from "@/components/Pagination";
import { useT } from "@/lib/i18n-context";
import { listAutotoolRuns, type AutotoolRunsPage } from "@/lib/autotool";

const STATUS_BADGE: Record<string, string> = {
  done: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  running: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  cancelled: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
  queued: "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30",
};

export default function AutotoolRunsPage() {
  const { t } = useT();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AutotoolRunsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await listAutotoolRuns(page, 20));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
    }
  }, [page, t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while any visible run is still in flight.
  useEffect(() => {
    if (!data) return;
    const inFlight = data.items.some((r) => ["queued", "running"].includes(r.status));
    if (!inFlight) return;
    const h = setInterval(refresh, 2000);
    return () => clearInterval(h);
  }, [data, refresh]);

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("autotoolRuns.heading")}
        </h1>
        <Link
          href="/publish/autotool"
          className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          {t("autotoolRuns.toConfig")}
        </Link>
      </div>

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {data && data.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-neutral-300 px-4 py-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          {t("autotoolRuns.empty")}
        </p>
      ) : data ? (
        <>
          <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
            <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
              <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  <th className="px-3 py-2">{t("autotoolRuns.colRun")}</th>
                  <th className="px-3 py-2">{t("autotoolRuns.colTable")}</th>
                  <th className="px-3 py-2">{t("autotoolRuns.colStatus")}</th>
                  <th className="px-3 py-2">{t("autotoolRuns.colProgress")}</th>
                  <th className="px-3 py-2">{t("autotoolRuns.colCreated")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                {data.items.map((r) => {
                  const processed = r.sent + r.failed + r.skipped;
                  const pct = Math.round((100 * processed) / Math.max(1, r.total));
                  return (
                    <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
                      <td className="px-3 py-2">
                        <Link
                          href={`/publish/autotool/runs/${r.id}`}
                          className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                        >
                          {t("autotoolRun.runHash", { id: r.id })}
                        </Link>
                      </td>
                      <td className="max-w-xs truncate px-3 py-2 text-neutral-700 dark:text-neutral-300">
                        {r.table_name || t("autotoolRun.tableFallback", { id: r.table_id ?? 0 })}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[r.status] ?? STATUS_BADGE.queued}`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
                            <div className="h-full bg-green-500" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs tabular-nums text-neutral-500 dark:text-neutral-400">
                            {processed}/{r.total}
                            {r.failed > 0 && (
                              <span className="ml-1 text-red-600 dark:text-red-400">
                                ({t("autotoolRun.failedShort", { count: r.failed })})
                              </span>
                            )}
                          </span>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={setPage}
          />
        </>
      ) : (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">{t("common.loading")}</p>
      )}
    </main>
  );
}
