"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getLanguageSyncRun,
  syncLanguages,
  type LanguageSyncResultRow,
  type LanguageSyncRunDetail,
  type LanguageSyncTarget,
} from "@/lib/publishLanguages";

/**
 * Pre-flight panel for Multi-mode bulk publish — shows which languages
 * each target site needs (derived from the table's domain × language
 * columns by the parent) and offers a one-click sync to each site's
 * `/index.php?__add_language=1` endpoint.
 *
 * The sync runs in the background now, so clicking Sync enqueues a run and
 * the panel polls it: a progress bar fills while the worker processes sites,
 * then each row shows its outcome. The user stays in the publish modal the
 * whole time (we never navigate away from mid-config). Never blocks the
 * parent's Publish submit.
 */
export function LanguageSync({
  targets,
}: {
  targets: LanguageSyncTarget[];
}) {
  const { t } = useT();
  const [enqueuing, setEnqueuing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<LanguageSyncRunDetail | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    },
    [],
  );

  if (targets.length === 0) return null;

  function safeMessage(e: unknown): string {
    const raw = e instanceof ApiError ? e.message : String(e);
    return typeof raw === "string"
      ? raw
      : (() => {
          try {
            return JSON.stringify(raw);
          } catch {
            return "Unknown error";
          }
        })();
  }

  function poll(runId: number) {
    getLanguageSyncRun(runId)
      .then((r) => {
        setRun(r);
        setEnqueuing(false);
        if (r.status !== "done") {
          pollRef.current = setTimeout(() => poll(runId), 2000);
        }
      })
      .catch((e) => {
        setError(safeMessage(e));
        setEnqueuing(false);
      });
  }

  async function onSync() {
    setEnqueuing(true);
    setError(null);
    setRun(null);
    if (pollRef.current) clearTimeout(pollRef.current);
    try {
      const trig = await syncLanguages(targets, "bulk_modal");
      poll(trig.run_id);
    } catch (e) {
      setError(safeMessage(e));
      setEnqueuing(false);
    }
  }

  const active = !!run && run.status !== "done";
  const syncing = enqueuing || active;
  const processed = run
    ? run.results.filter((r) => r.state === "done").length
    : 0;
  const pct =
    run && run.total_count > 0
      ? Math.round((processed / run.total_count) * 100)
      : syncing
        ? 5
        : 0;

  const okCount = run?.ok_count ?? 0;
  const failCount = run?.fail_count ?? 0;
  const skipCount = run?.skip_count ?? 0;

  return (
    <section className="space-y-3 rounded-md border border-blue-200 bg-blue-50 p-3 dark:border-blue-900/60 dark:bg-blue-950/30">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-blue-900 dark:text-blue-200">
            {t("langSync.title")}
          </h3>
          <p className="mt-0.5 text-xs text-blue-800/80 dark:text-blue-200/70">
            {t("langSync.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={onSync}
          disabled={syncing}
          className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-60 dark:bg-blue-500"
        >
          {syncing
            ? t("langSync.syncing")
            : t("langSync.syncButton", { count: targets.length })}
        </button>
      </header>

      {/* Preview list — what we'll send, before the user clicks. */}
      {!run && !enqueuing && (
        <ul className="max-h-32 space-y-1 overflow-auto text-xs">
          {targets.slice(0, 10).map((tgt) => (
            <li
              key={tgt.domain_name}
              className="flex items-center justify-between gap-3 font-mono text-blue-900/80 dark:text-blue-200/80"
            >
              <span className="truncate">{tgt.domain_name}</span>
              <span className="shrink-0 tabular-nums">
                {tgt.languages.join(", ")}
              </span>
            </li>
          ))}
          {targets.length > 10 && (
            <li className="text-blue-700/70 dark:text-blue-300/70">
              {t("bulkPub.andMore", { count: targets.length - 10 })}
            </li>
          )}
        </ul>
      )}

      {/* Progress bar while the run is queued/running. */}
      {syncing && (
        <div>
          <p className="mb-1 text-xs text-blue-900/80 dark:text-blue-200/70">
            {run
              ? t("langPage.runProgress", {
                  done: processed,
                  total: run.total_count,
                })
              : t("langSync.syncing")}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-200/60 dark:bg-blue-900/60">
            <div
              className="h-full bg-blue-600 transition-[width] duration-300 dark:bg-blue-400"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Result list — appears as the run progresses + after it finishes. */}
      {run && (
        <>
          <p className="text-xs font-medium text-blue-900 dark:text-blue-200">
            {t("langSync.summary", {
              ok: okCount,
              fail: failCount,
              skip: skipCount,
            })}
          </p>
          <ul className="max-h-40 space-y-1 overflow-auto text-xs">
            {run.results.map((r) => (
              <li
                key={r.id}
                className="flex items-start justify-between gap-3"
              >
                <span className="flex-1 truncate font-mono">
                  <ResultBadge r={r} /> {r.domain_name}
                </span>
                <span
                  className="shrink-0 max-w-[60%] truncate text-right text-[11px] text-neutral-600 dark:text-neutral-400"
                  title={r.detail || r.skip_reason || ""}
                >
                  {r.state === "pending"
                    ? t("langPage.resultPending")
                    : r.skipped
                      ? (r.skip_reason ?? t("langSync.skipped"))
                      : r.status_code != null
                        ? `HTTP ${r.status_code}${r.elapsed_ms != null ? ` · ${r.elapsed_ms}ms` : ""}`
                        : (r.detail ?? "")}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {error && (
        <p className="rounded bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {/* Deep-link to the persistent history. The specific-run link appears
          once we have a run id (handy for jumping to Retry-failed there). */}
      <div className="flex items-center justify-end gap-3 text-[11px]">
        {run && (
          <Link
            href={`/publish/languages/${run.id}`}
            className="text-blue-700 hover:underline dark:text-blue-300"
          >
            {t("langSync.viewThisRun")}
          </Link>
        )}
        <Link
          href="/publish/languages"
          className="text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("langSync.viewHistory")}
        </Link>
      </div>
    </section>
  );
}

function ResultBadge({ r }: { r: LanguageSyncResultRow }) {
  if (r.state === "pending") {
    return <span className="text-blue-500 dark:text-blue-300">○</span>;
  }
  if (r.skipped) {
    return <span className="text-neutral-500 dark:text-neutral-400">—</span>;
  }
  if (r.ok) {
    return <span className="text-green-700 dark:text-green-400">●</span>;
  }
  return <span className="text-red-600 dark:text-red-400">●</span>;
}
