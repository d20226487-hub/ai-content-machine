"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { listPublishJobs, type PublishJob } from "@/lib/publish";

const STATUS_BADGE: Record<string, string> = {
  posted: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  posting: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  queued: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
};

export default function PostPage() {
  const { t } = useT();
  const [jobs, setJobs] = useState<PublishJob[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPublishJobs({ page, page_size: pageSize })
      .then((r) => {
        setJobs(r.items);
        setTotal(r.total);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : t("common.failedToLoad")));
  }, [page, pageSize, t]);

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("pubHistory.title")}
        </h1>
        <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
          {t("pubHistory.subtitle", { count: total.toLocaleString() })}
        </p>
      </div>

      {error && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("pubHistory.colTime")}</th>
              <th className="px-3 py-2">{t("pubHistory.colDomain")}</th>
              <th className="px-3 py-2">{t("pubHistory.colProfile")}</th>
              <th className="px-3 py-2">{t("pubHistory.colStatus")}</th>
              <th className="px-3 py-2">{t("pubHistory.colLang")}</th>
              <th className="px-3 py-2">{t("pubHistory.colPost")}</th>
              <th className="px-3 py-2">{t("pubHistory.colError")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {jobs === null && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-neutral-500">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {jobs !== null && jobs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-neutral-500">
                  {t("pubHistory.empty")}
                </td>
              </tr>
            )}
            {jobs?.map((j) => (
              <tr key={j.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
                <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                  {new Date(j.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-neutral-800 dark:text-neutral-200">
                  {j.domain_name ?? t("pubHistory.deletedDomain")}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                  {j.profile_name ?? "—"}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_BADGE[j.status] ?? STATUS_BADGE.queued}`}
                  >
                    {j.status}
                  </span>
                  {j.warnings && j.warnings.length > 0 && (
                    <span
                      title={j.warnings.join("\n")}
                      className="ml-1 inline-flex items-center rounded bg-amber-50 px-1 py-0.5 text-[10px] font-medium ring-1 ring-amber-600/10 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 dark:ring-amber-400/30"
                    >
                      ⚠ {j.warnings.length}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                  {j.language ?? "—"}
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
                <td className="max-w-md truncate px-3 py-2 text-xs" title={j.error ?? (j.warnings?.join("\n") ?? undefined)}>
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
      {total > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-600 dark:text-neutral-400">
          <span>
            {t("common.showingRange", {
              from: (page - 1) * pageSize + 1,
              to: Math.min(page * pageSize, total),
              total,
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
            <span>{t("common.pageXslashY", { page, total: Math.max(1, Math.ceil(total / pageSize)) })}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * pageSize >= total}
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
