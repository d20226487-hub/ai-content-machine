"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  syncLanguages,
  type LanguageSyncOneResult,
  type LanguageSyncTarget,
} from "@/lib/publishLanguages";

/**
 * Pre-flight panel for Multi-mode bulk publish — shows which languages
 * each target site needs (derived from the table's domain × language
 * columns by the parent) and offers a one-click POST to each site's
 * `/index.php?__add_language=1` endpoint.
 *
 * The component is read-only with respect to the targets — it neither
 * filters them nor groups them. That's the parent's job. Here we just
 * render the preview + drive the request + show per-domain results.
 *
 * Designed to be optional: if the user skips this and clicks Publish,
 * the publish itself will still try and fail per-row for missing
 * languages — they can come back and run sync later. So the button
 * never blocks the parent's submit flow.
 */
export function LanguageSync({
  targets,
}: {
  targets: LanguageSyncTarget[];
}) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<LanguageSyncOneResult[] | null>(null);
  // Captured after a successful sync so we can deep-link "View this run"
  // straight to the history detail page. null until the first sync lands.
  const [lastRunId, setLastRunId] = useState<number | null>(null);

  if (targets.length === 0) return null;

  async function onSync() {
    setBusy(true);
    setError(null);
    setResults(null);
    setLastRunId(null);
    try {
      const r = await syncLanguages(targets, "bulk_modal");
      setResults(r.results);
      setLastRunId(r.run_id);
    } catch (e) {
      // `e.message` from ApiError carries whatever the backend put in the
      // response's `detail` field. For a 422 that's actually an array of
      // validation errors, not a string — coerce via JSON.stringify so we
      // never render `[object Object]` to the user.
      const raw = e instanceof ApiError ? e.message : String(e);
      const safe =
        typeof raw === "string" ? raw : (() => { try { return JSON.stringify(raw); } catch { return "Unknown error"; } })();
      setError(safe);
    } finally {
      setBusy(false);
    }
  }

  const okCount = results?.filter((r) => r.ok).length ?? 0;
  const failCount = results?.filter((r) => !r.ok && !r.skipped).length ?? 0;
  const skipCount = results?.filter((r) => r.skipped).length ?? 0;

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
          disabled={busy}
          className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-60 dark:bg-blue-500"
        >
          {busy
            ? t("langSync.syncing")
            : t("langSync.syncButton", { count: targets.length })}
        </button>
      </header>

      {/* Preview list — what we'll send, before the user clicks. */}
      {!results && !busy && (
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

      {/* Result list — replaces preview after a sync completes. */}
      {results && (
        <>
          <p className="text-xs font-medium text-blue-900 dark:text-blue-200">
            {t("langSync.summary", {
              ok: okCount,
              fail: failCount,
              skip: skipCount,
            })}
          </p>
          <ul className="max-h-40 space-y-1 overflow-auto text-xs">
            {results.map((r) => (
              <li
                key={r.domain_name}
                className="flex items-start justify-between gap-3"
              >
                <span className="flex-1 truncate font-mono">
                  <ResultBadge r={r} /> {r.domain_name}
                </span>
                <span
                  className="shrink-0 max-w-[60%] truncate text-right text-[11px] text-neutral-600 dark:text-neutral-400"
                  title={r.detail || r.skip_reason || ""}
                >
                  {r.skipped
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

      {/* Deep-link to the persistent history. Hidden until a sync runs;
          once we have a run_id we surface BOTH a link to that specific
          run (useful right after seeing the inline summary) and the
          general history index. */}
      <div className="flex items-center justify-end gap-3 text-[11px]">
        {lastRunId != null && (
          <Link
            href={`/publish/languages/${lastRunId}`}
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

function ResultBadge({ r }: { r: LanguageSyncOneResult }) {
  if (r.skipped) {
    return <span className="text-neutral-500 dark:text-neutral-400">—</span>;
  }
  if (r.ok) {
    return <span className="text-green-700 dark:text-green-400">●</span>;
  }
  return <span className="text-red-600 dark:text-red-400">●</span>;
}
