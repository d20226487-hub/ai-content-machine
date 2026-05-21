"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getLanguageSyncRun,
  type LanguageSyncRunDetail,
} from "@/lib/publishLanguages";

/**
 * Detail page for one persisted language-sync run.
 *
 * Reads the full result list (no pagination — a single run usually has
 * a few dozen rows at most) and renders a table with one row per target
 * site: which languages we attempted to upsert, the upstream HTTP status,
 * the raw response body, elapsed ms. Failed runs surface the same
 * upstream `error` field the inline panel shows in the modal, just
 * persisted so you can come back to it later.
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

  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setLoadError("Invalid run id");
      return;
    }
    let cancelled = false;
    getLanguageSyncRun(runId)
      .then((r) => {
        if (!cancelled) setRun(r);
      })
      .catch((e) => {
        if (!cancelled)
          setLoadError(e instanceof ApiError ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

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
          <header>
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
          </header>

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
                      <StatusBadge
                        ok={r.ok}
                        skipped={r.skipped}
                        statusCode={r.status_code}
                      />
                    </td>
                    <td className="px-3 py-2 text-xs tabular-nums text-neutral-600 dark:text-neutral-400">
                      {r.elapsed_ms != null ? `${r.elapsed_ms}ms` : "—"}
                    </td>
                    <td className="max-w-md px-3 py-2 text-xs">
                      {r.skipped ? (
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

function StatusBadge({
  ok,
  skipped,
  statusCode,
}: {
  ok: boolean;
  skipped: boolean;
  statusCode: number | null;
}) {
  const { t } = useT();
  if (skipped) {
    return (
      <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-700 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600">
        {t("langPage.resultSkipped")}
      </span>
    );
  }
  if (ok) {
    return (
      <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700 ring-1 ring-inset ring-green-600/20 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30">
        {t("langPage.resultOk")}
        {statusCode != null ? ` · ${statusCode}` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 ring-1 ring-inset ring-red-600/20 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30">
      {t("langPage.resultFail")}
      {statusCode != null ? ` · ${statusCode}` : ""}
    </span>
  );
}
