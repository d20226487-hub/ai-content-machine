"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  LanguageCsvImportModal,
  type ImportedRow,
} from "@/components/publishLanguages/LanguageCsvImportModal";
import { MultiDomainPicker } from "@/components/publishLanguages/MultiDomainPicker";
import { ApiError } from "@/lib/api";
import type { DomainPickerItem } from "@/lib/domains";
import { useT } from "@/lib/i18n-context";
import {
  listLanguageSyncRuns,
  syncLanguages,
  type LanguageSyncOneResult,
  type LanguageSyncRun,
  type LanguageSyncTarget,
} from "@/lib/publishLanguages";

// Page-size options for the history table. Smaller scale than the
// Domains page (50/100/200) because language sync runs accumulate
// far more slowly than domains — a 25-row default fits most users'
// recent-activity scan, and 100 covers the long tail.
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
const DEFAULT_PAGE_SIZE: (typeof PAGE_SIZE_OPTIONS)[number] = 25;

/**
 * Standalone home for the language-sync feature.
 *
 *   • Top: a small form to fire an ad-hoc sync against any Custom CMS
 *     domain — pick the site from the combobox, paste a language list,
 *     hit Sync. No bulk table required.
 *   • Bottom: paginated history of every past sync (also the destination
 *     for the "View this run" deep-link from the pre-flight panel in
 *     BulkPublishModal).
 *
 * The page is a thin orchestrator — the actual POST + result rendering
 * are shared with the modal panel via the LanguageSync sub-flow.
 */
export default function LanguagesPage() {
  const { t } = useT();

  // History list state. Paginated against the backend's
  // /publish/languages/runs endpoint (`page`, `page_size`, returns
  // `total`). Pre-2026-05-23 we hardcoded (1, 100) and rendered all
  // rows — after 100 historical sync runs the rest became invisible.
  const [runs, setRuns] = useState<LanguageSyncRun[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<
    (typeof PAGE_SIZE_OPTIONS)[number]
  >(DEFAULT_PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Reset to page 1 when page-size changes — otherwise a user on page 5
  // of size=10 (total 50) switching to size=100 lands on page 5 of an
  // empty result set.
  useEffect(() => {
    setPage(1);
  }, [pageSize]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listLanguageSyncRuns(page, pageSize)
      .then((r) => {
        if (cancelled) return;
        setRuns(r.items);
        setTotal(r.total);
        setLoadError(null);
      })
      .catch((e) => {
        if (!cancelled)
          setLoadError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick, page, pageSize]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const hasMore = page < totalPages;

  return (
    <div className="space-y-6 p-5">
      <header>
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("langPage.title")}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("langPage.subtitle")}
        </p>
      </header>

      <NewSyncForm onCreated={() => setReloadTick((n) => n + 1)} />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {t("langPage.historyTitle")}
        </h2>
        {loadError && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {loadError}
          </p>
        )}
        {runs && runs.length === 0 && page === 1 && (
          <p className="rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-6 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
            {t("langPage.historyEmpty")}
          </p>
        )}
        {runs && runs.length > 0 && <RunsTable runs={runs} />}
        {/* Pagination footer. Hidden when the result set fits on one
            page AND we're on page 1 — keeps the "Page 1 of 1" line off
            small / empty histories. Same shape as the Domains page so
            the two paginated lists feel consistent. */}
        {runs !== null && (total > pageSize || page > 1) && (
          <div className="mt-2 flex items-center justify-between text-xs text-neutral-600 dark:text-neutral-400">
            <div className="flex items-center gap-2">
              <span>{t("domains.pageSizeLabel")}</span>
              <select
                value={pageSize}
                onChange={(e) =>
                  setPageSize(
                    Number(e.target.value) as (typeof PAGE_SIZE_OPTIONS)[number],
                  )
                }
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3">
              <span className="tabular-nums">
                {t("domains.pageOfTotal", { page, total: totalPages })}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="rounded-md border border-neutral-300 px-2 py-0.5 disabled:opacity-40 dark:border-neutral-700"
              >
                {t("common.prev")}
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore || loading}
                className="rounded-md border border-neutral-300 px-2 py-0.5 disabled:opacity-40 dark:border-neutral-700"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function RunsTable({ runs }: { runs: LanguageSyncRun[] }) {
  const { t } = useT();
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
        <thead className="bg-neutral-50 dark:bg-neutral-900/50">
          <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            <th className="px-3 py-2 w-12">#</th>
            <th className="px-3 py-2">{t("langPage.colWhen")}</th>
            <th className="px-3 py-2">{t("langPage.colBy")}</th>
            <th className="px-3 py-2">{t("langPage.colSource")}</th>
            <th className="px-3 py-2">{t("langPage.colTotals")}</th>
            <th className="px-3 py-2 text-right" />
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {runs.map((r) => (
            <tr key={r.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/50">
              <td className="px-3 py-2 font-mono text-xs text-neutral-500">{r.id}</td>
              <td className="px-3 py-2 text-xs">
                {new Date(r.created_at).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-xs">{r.created_by_name ?? "—"}</td>
              <td className="px-3 py-2 text-xs">
                <SourceBadge source={r.source} />
              </td>
              <td className="px-3 py-2 text-xs">
                <Counts run={r} />
              </td>
              <td className="px-3 py-2 text-right text-xs">
                <Link
                  href={`/publish/languages/${r.id}`}
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {t("langPage.viewLink")}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const { t } = useT();
  const label =
    source === "bulk_modal"
      ? t("langPage.sourceBulkModal")
      : source === "standalone"
        ? t("langPage.sourceStandalone")
        : source;
  return (
    <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-700 ring-1 ring-inset ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600">
      {label}
    </span>
  );
}

function Counts({ run }: { run: LanguageSyncRun }) {
  return (
    <span className="space-x-2 font-mono tabular-nums">
      <span title="total">{run.total_count}</span>
      {run.ok_count > 0 && (
        <span className="text-green-700 dark:text-green-400" title="ok">
          ●{run.ok_count}
        </span>
      )}
      {run.fail_count > 0 && (
        <span className="text-red-600 dark:text-red-400" title="failed">
          ●{run.fail_count}
        </span>
      )}
      {run.skip_count > 0 && (
        <span className="text-neutral-500 dark:text-neutral-400" title="skipped">
          —{run.skip_count}
        </span>
      )}
    </span>
  );
}

/**
 * "Run a new sync" form — multi-site capable.
 *
 * Two modes share one form:
 *   * Shared (default) — one textarea, applied to every picked domain.
 *     Covers "add Arabic to all 12 sites" — the common case.
 *   * Per-site — each chip expands into its own textarea, so different
 *     sites can get different language sets in the same run.
 *
 * The submitted batch becomes ONE LanguageSyncRun with N result rows
 * (one per domain) — that's the unit the history page paginates by.
 *
 * Picker: `MultiDomainPicker` (chip list + search + checkbox popover).
 * Custom-CMS-only because the upstream endpoint is.
 */
function NewSyncForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useT();
  const [picked, setPicked] = useState<DomainPickerItem[]>([]);
  // Mode toggle: false = shared textarea, true = per-site textareas.
  const [perSite, setPerSite] = useState(false);
  const [sharedLangs, setSharedLangs] = useState("");
  // Per-site language input, keyed by domain id. Lazily populated as
  // the user types into a chip's textarea. Missing key + perSite mode
  // means "no languages typed yet" → that target is skipped at submit.
  const [siteLangs, setSiteLangs] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{
    runId: number;
    results: LanguageSyncOneResult[];
  } | null>(null);
  // CSV import modal toggle. The modal does the heavy lifting (parse +
  // resolve + hard-fail on unknowns); on Apply it hands back N enriched
  // rows that we plug straight into picked + siteLangs + perSite=true.
  const [importOpen, setImportOpen] = useState(false);

  function onImported(rows: ImportedRow[]) {
    // Replace current picks rather than append — a 100-row CSV merged
    // into existing manual picks would be surprising. The user can
    // cancel before applying if they want to keep their current state.
    const newPicked: DomainPickerItem[] = rows.map((r) => ({
      id: r.domain_id,
      name: r.domain_name,
      has_credentials: r.has_credentials,
      // The other DomainPickerItem fields aren't used in chip render —
      // safe to fill with sensible defaults. cms_type=custom because
      // the resolve endpoint only returns Custom CMS by design.
      base_url: "",
      cms_type: "custom" as const,
      auth_type: "basic_auth" as const,
      languages: [],
      multilingual_plugin: "none" as const,
      folder_id: null,
    }));
    const newSiteLangs: Record<number, string> = {};
    for (const r of rows) newSiteLangs[r.domain_id] = r.languages.join(", ");
    setPicked(newPicked);
    setSiteLangs(newSiteLangs);
    setPerSite(true); // CSV implies per-site languages
    setImportOpen(false);
  }

  function parseLangs(text: string): string[] {
    // Accept commas, newlines, semicolons, spaces — flatten to a tidy set.
    return Array.from(
      new Set(
        text
          .split(/[\s,;]+/)
          .map((s) => s.trim().toLowerCase())
          .filter(Boolean),
      ),
    ).sort();
  }

  const sharedParsed = parseLangs(sharedLangs);

  // Build the target list the way the backend expects. In shared mode
  // every chip gets the same language list; in per-site mode each chip
  // contributes its own (and chips with no languages typed are dropped
  // — keeping the submitted batch honest with what was actually filled).
  const targets: LanguageSyncTarget[] = perSite
    ? picked
        .map((d) => ({
          domain_name: d.name,
          languages: parseLangs(siteLangs[d.id] ?? ""),
        }))
        .filter((t) => t.languages.length > 0)
    : sharedParsed.length > 0
      ? picked.map((d) => ({ domain_name: d.name, languages: sharedParsed }))
      : [];

  const canSubmit = targets.length > 0 && !busy;

  function removeChip(id: number) {
    setPicked((cur) => cur.filter((d) => d.id !== id));
    setSiteLangs((cur) => {
      const next = { ...cur };
      delete next[id];
      return next;
    });
  }

  async function onSubmit() {
    if (targets.length === 0) return;
    setBusy(true);
    setError(null);
    setLastResult(null);
    try {
      const r = await syncLanguages(targets, "standalone");
      setLastResult({ runId: r.run_id, results: r.results });
      onCreated();
    } catch (e) {
      const raw = e instanceof ApiError ? e.message : String(e);
      const safe =
        typeof raw === "string"
          ? raw
          : (() => {
              try {
                return JSON.stringify(raw);
              } catch {
                return "Unknown error";
              }
            })();
      setError(safe);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
        {t("langPage.newSyncTitle")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("langPage.newSyncHint")}
      </p>

      {/* Multi-domain picker (popover with search + checkboxes), plus
          an "Import CSV" shortcut for fleets large enough that typing
          rows in by hand is no fun. */}
      <div className="mt-3">
        <div className="flex items-end justify-between gap-3">
          <span className="block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("langPage.fieldDomains")}
          </span>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t("langPage.importCsv")}
          </button>
        </div>
        <div className="mt-1">
          <MultiDomainPicker value={picked} onChange={setPicked} />
        </div>
      </div>

      {/* Picked chips. Removable. In per-site mode each chip ALSO carries
          its own language textarea right below it. */}
      {picked.length > 0 && (
        <div className="mt-3 space-y-2">
          {picked.map((d) => (
            <div key={d.id} className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800 ring-1 ring-inset ring-blue-300 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-500/30">
                  <span className="font-mono">{d.name}</span>
                  <button
                    type="button"
                    onClick={() => removeChip(d.id)}
                    className="ml-1 text-blue-600 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100"
                    aria-label={t("langPage.chipRemove")}
                  >
                    ×
                  </button>
                </span>
              </div>
              {perSite && (
                <textarea
                  value={siteLangs[d.id] ?? ""}
                  onChange={(e) =>
                    setSiteLangs((cur) => ({ ...cur, [d.id]: e.target.value }))
                  }
                  rows={2}
                  placeholder={t("langPage.languagesPlaceholder")}
                  className="ml-2 block w-[calc(100%-0.5rem)] rounded-md border border-neutral-300 bg-white px-3 py-1.5 font-mono text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Mode toggle — shared vs per-site. Hidden until at least one
          domain is picked, since the toggle has no meaning with zero
          chips. */}
      {picked.length > 0 && (
        <label className="mt-3 flex items-center gap-2 text-xs text-neutral-700 dark:text-neutral-300">
          <input
            type="checkbox"
            checked={perSite}
            onChange={(e) => setPerSite(e.target.checked)}
          />
          {t("langPage.overridePerSite")}
        </label>
      )}

      {/* Shared-mode language input. Hidden when perSite is on (each
          chip has its own textarea then). */}
      {!perSite && picked.length > 0 && (
        <label className="mt-3 block">
          <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("langPage.fieldLanguages")}
          </span>
          <textarea
            value={sharedLangs}
            onChange={(e) => setSharedLangs(e.target.value)}
            rows={3}
            placeholder={t("langPage.languagesPlaceholder")}
            className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          {sharedParsed.length > 0 && (
            <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
              {t("langPage.willApplyToCount", {
                count: picked.length,
                langs: sharedParsed.join(", "),
              })}
            </p>
          )}
        </label>
      )}

      {error && (
        <p className="mt-3 rounded bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {lastResult && (
        <div className="mt-3 rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs dark:border-neutral-800 dark:bg-neutral-950/40">
          <ul className="space-y-1">
            {lastResult.results.map((r) => (
              <li
                key={r.domain_name}
                className={
                  r.skipped
                    ? "text-neutral-500"
                    : r.ok
                      ? "text-green-700 dark:text-green-400"
                      : "text-red-700 dark:text-red-400"
                }
              >
                ● <span className="font-mono">{r.domain_name}</span>
                {r.status_code != null ? ` · HTTP ${r.status_code}` : ""}
                {r.skipped && r.skip_reason ? ` — ${r.skip_reason}` : ""}
              </li>
            ))}
          </ul>
          <Link
            href={`/publish/languages/${lastResult.runId}`}
            className="mt-2 inline-block text-blue-600 hover:underline dark:text-blue-400"
          >
            {t("langSync.viewThisRun")}
          </Link>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between">
        <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
          {targets.length > 0
            ? t("langPage.willSyncCount", { count: targets.length })
            : ""}
        </p>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={onSubmit}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 dark:bg-blue-500"
        >
          {busy ? t("langPage.runningSync") : t("langPage.startSync")}
        </button>
      </div>

      {importOpen && (
        <LanguageCsvImportModal
          onClose={() => setImportOpen(false)}
          onImported={onImported}
        />
      )}
    </section>
  );
}
