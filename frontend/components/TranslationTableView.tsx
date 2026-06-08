"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  dismissTranslationErrors,
  getTranslationTable,
  replaceTranslationLinks,
  restoreTranslationErrors,
  type LinkTypeCategory,
  type LinkTypeFilter,
  type TranslationLinkTag,
  type TranslationTableRow,
  type TranslationTableView as TView,
} from "@/lib/linkCheck";

const PAGE_SIZE = 25;
// Page size used when sweeping every page for "select all matches" — matches
// the endpoint's max so the fewest requests cover the whole (bounded) table.
const MAX_FETCH = 200;

const errKey = (rowId: number, url: string) => `${rowId}|${url}`;
const splitKey = (k: string): { row_id: number; link: string } => {
  const i = k.indexOf("|");
  return { row_id: Number(k.slice(0, i)), link: k.slice(i + 1) };
};

// Restored strong green in LIGHT mode; only DARK mode is toned down.
const GREEN = "text-emerald-700 dark:text-emerald-500/90";
const RED = "text-red-600 dark:text-red-400";
const GREY = "text-neutral-500 dark:text-neutral-400";
const NEUTRAL = "text-neutral-700 dark:text-neutral-300";

function kindCls(kind: TranslationLinkTag["kind"]): string {
  return kind === "discrepancy" ? RED : kind === "invented" ? GREY : GREEN;
}

/** Registrable-ish host (lowercased, any leading www. collapsed) or null when
 *  unparseable — so a doubled-www typo (``www.www.fifa.com``) still counts as
 *  the same host as ``www.fifa.com`` and gets the inline diff rather than a
 *  blanket-red link. */
function hostOf(u: string): string | null {
  try {
    let h = new URL(u).hostname.toLowerCase();
    while (h.startsWith("www.")) h = h.slice(4);
    return h;
  } catch {
    return null;
  }
}

function sameHost(a: string, b: string): boolean {
  const ha = hostOf(a);
  const hb = hostOf(b);
  return ha !== null && ha === hb;
}

type UrlDiffSeg = { text: string; kind: "equal" | "del" | "ins" };

/** Split a URL into diffable tokens: each run of label chars and each ``/`` or
 *  ``.`` delimiter is its own token, so the diff lands on whole segments — a
 *  language seg (``en`` vs ``es``), a missing ``/en/``, or an extra ``www.``
 *  in the host — rather than scattered characters. */
function tokenizeUrl(u: string): string[] {
  return u.match(/[^/.]+|[/.]/g) ?? [];
}

/** Token-level unified diff of a translation link against what it should have
 *  been. ``del`` = a token present in the actual link but not expected (extra,
 *  struck through); ``ins`` = a token expected but missing from the actual link
 *  (e.g. the ``en`` language segment, shown underlined); ``equal`` = shared. */
function urlDiff(expected: string, actual: string): UrlDiffSeg[] {
  const a = tokenizeUrl(actual);
  const b = tokenizeUrl(expected);
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] =
        a[i] === b[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);

  const out: UrlDiffSeg[] = [];
  const push = (text: string, kind: UrlDiffSeg["kind"]) => {
    if (!text) return;
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ text, kind });
  };
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      push(a[i], "equal");
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push(a[i], "del");
      i++;
    } else {
      push(b[j], "ins");
      j++;
    }
  }
  while (i < m) push(a[i++], "del");
  while (j < n) push(b[j++], "ins");
  return out;
}

/** The raw translation-links table for a run. ``discrepancyLinksOnly`` hides
 *  the OK (green) links so each row shows only its problem links — used on the
 *  run page as a focused overview. The full version (every link) backs the
 *  standalone raw-table page. */
export function TranslationTableView({
  runId,
  tableId,
  discrepancyLinksOnly = false,
  onFixRows,
}: {
  runId: number;
  /** Needed to open the resulting replace job's detail page. */
  tableId: number;
  discrepancyLinksOnly?: boolean;
  /** When provided, a "Fix with AI" button appears in the selection bar and
   *  calls this with the distinct selected row ids plus the active link-type
   *  filter (so the fix is scoped to the same links the table is showing). */
  onFixRows?: (rowIds: number[], linkType: LinkTypeFilter) => void;
}) {
  const { t } = useT();
  const router = useRouter();

  const [rows, setRows] = useState<TranslationTableRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [view, setView] = useState<TView>("active");
  const [linkType, setLinkType] = useState<LinkTypeFilter>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [selectingAll, setSelectingAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Reset to page 1 AND clear the selection when the view or link-type filter
  // changes — both change which errors are selectable and the action semantics
  // (active = dismiss, dismissed = restore). Crucially, do NOT clear on
  // pagination: selection keys (`rowId|url`) are globally unique, so the
  // selection persists across pages and a bulk action applies to every page.
  useEffect(() => {
    setPage(1);
    setSelected(new Set());
  }, [view, linkType]);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const r = await getTranslationTable(runId, p, PAGE_SIZE, view, linkType);
        setRows(r.items);
        setTotal(r.total_rows);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [runId, view, linkType],
  );

  useEffect(() => {
    if (Number.isFinite(runId)) void load(page);
  }, [runId, page, load]);

  const selectable = view === "active" || view === "dismissed";
  // The one predicate for "is this link selectable in the current view" — used
  // for both the per-page keys and the across-all-pages select, so the two can
  // never disagree (active = live errors, dismissed = dismissed).
  const isSelectableLink = useCallback(
    (l: TranslationLinkTag) =>
      l.kind !== "ok" &&
      !l.resolved &&
      (view === "dismissed" ? l.dismissed : !l.dismissed),
    [view],
  );
  // Every selectable error key on the CURRENT page.
  const pageKeys = useMemo(
    () =>
      rows.flatMap((r) =>
        r.translation.filter(isSelectableLink).map((l) => errKey(r.row_id, l.url)),
      ),
    [rows, isSelectableLink],
  );
  const allSelected = pageKeys.length > 0 && pageKeys.every((k) => selected.has(k));

  // Select EVERY matching link across all pages: page through at the max size
  // and add each selectable key, merging into the existing selection. Reuses
  // the same data + predicate as the table, so it stays in sync.
  async function selectAllMatches() {
    if (selectingAll) return;
    setSelectingAll(true);
    setError(null);
    try {
      const keys = new Set(selected);
      let p = 1;
      for (;;) {
        const r = await getTranslationTable(runId, p, MAX_FETCH, view, linkType);
        for (const row of r.items) {
          for (const l of row.translation) {
            if (isSelectableLink(l)) keys.add(errKey(row.row_id, l.url));
          }
        }
        if (r.items.length === 0 || p * MAX_FETCH >= r.total_rows) break;
        p += 1;
      }
      setSelected(keys);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSelectingAll(false);
    }
  }

  // The selection is per-link; replace/AI-fix act per cell (one job-cell per
  // row), so surface both units to bridge the link count and the row count.
  const selectedRowCount = useMemo(
    () => new Set(Array.from(selected).map((k) => splitKey(k).row_id)).size,
    [selected],
  );

  function toggle(k: string) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }
  function toggleAll() {
    // Add/remove only THIS page's keys, preserving selections made on other
    // pages — the keys (`rowId|url`) are globally unique, so the count
    // compounds across pages (page 1 + page 2 = both, not just the latest).
    setSelected((cur) => {
      const next = new Set(cur);
      if (pageKeys.every((k) => cur.has(k))) {
        for (const k of pageKeys) next.delete(k);
      } else {
        for (const k of pageKeys) next.add(k);
      }
      return next;
    });
  }

  async function applyAction() {
    if (selected.size === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const items = Array.from(selected).map(splitKey);
      if (view === "dismissed") await restoreTranslationErrors(runId, items);
      else await dismissTranslationErrors(runId, items);
      setSelected(new Set());
      await load(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // Swap each selected wrong link for its expected link, in the cell itself —
  // recorded as a revertable replace job; open its detail page on success.
  async function applyReplace() {
    if (selected.size === 0 || busy) return;
    if (!window.confirm(t("linkCheckRun.confirmReplace", { n: selected.size })))
      return;
    setBusy(true);
    setError(null);
    try {
      const items = Array.from(selected).map(splitKey);
      const run = await replaceTranslationLinks(runId, items);
      setSelected(new Set());
      router.push(`/library/${tableId}/link-fix/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={view}
          onChange={(e) => setView(e.target.value as TView)}
          className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="active">{t("linkCheckRun.rawViewActive")}</option>
          {/* "All rows" would show rows with no problem links — pointless when
              the OK links are hidden, so it's dropped in discrepancy-only mode. */}
          {!discrepancyLinksOnly && (
            <option value="all">{t("linkCheckRun.rawViewAll")}</option>
          )}
          <option value="dismissed">{t("linkCheckRun.rawViewDismissed")}</option>
          <option value="solved">{t("linkCheckRun.rawViewSolved")}</option>
        </select>
        <select
          value={linkType}
          onChange={(e) => setLinkType(e.target.value as LinkTypeFilter)}
          className="rounded-md border border-neutral-300 px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="all">{t("linkCheckRun.rawTypeAll")}</option>
          <option value="product">{t("linkCheckRun.rawTypeProduct")}</option>
          <option value="internal">{t("linkCheckRun.rawTypeInternal")}</option>
          <option value="external">{t("linkCheckRun.rawTypeExternal")}</option>
        </select>
        <span className="flex flex-wrap items-center gap-3 text-[11px] text-neutral-500 dark:text-neutral-400">
          {!discrepancyLinksOnly && (
            <LegendDot cls="bg-emerald-500" label={t("linkCheckRun.rawLegendOk")} />
          )}
          <LegendDot cls="bg-neutral-400" label={t("linkCheckRun.rawLegendInvented")} />
          <span className="inline-flex items-center gap-1">
            <span className="text-red-600 underline decoration-2 underline-offset-2 dark:text-red-400">
              abc
            </span>
            {t("linkCheckRun.rawLegendUnderline")}
          </span>
        </span>
        {selectable && total > 0 && (
          <button
            type="button"
            onClick={selectAllMatches}
            disabled={selectingAll || loading}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-violet-300 px-2.5 py-1.5 text-xs font-medium text-violet-700 hover:bg-violet-50 disabled:opacity-60 dark:border-violet-700 dark:text-violet-300 dark:hover:bg-violet-900/30"
          >
            {selectingAll && <Spinner />}
            {t("linkCheckRun.selectAllMatches")}
          </button>
        )}
      </div>

      {selectable && selected.size > 0 && (
        <div className="mt-3 flex items-center gap-3 rounded-md border border-violet-200 bg-violet-50 px-3 py-2 text-sm dark:border-violet-900/40 dark:bg-violet-950/20">
          <span className="text-violet-800 dark:text-violet-200">
            {t("linkCheckRun.selectedErrorsRows", {
              n: selected.size,
              rows: selectedRowCount,
            })}
          </span>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            disabled={busy}
            className="text-xs font-medium text-violet-700 underline-offset-2 hover:underline disabled:opacity-60 dark:text-violet-300"
          >
            {t("linkCheckRun.clearSelection")}
          </button>
          <div className="ml-auto flex items-center gap-2">
            {/* Replace is offered only on the discrepancy-only overview, for
                live errors — it rewrites the wrong link to the expected one. */}
            {discrepancyLinksOnly && view === "active" && (
              <button
                type="button"
                onClick={applyReplace}
                disabled={busy}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                {t("linkCheckRun.replaceSelected", { n: selected.size })}
              </button>
            )}
            {onFixRows && view === "active" && (
              <button
                type="button"
                onClick={() => {
                  const rowIds = Array.from(
                    new Set(
                      Array.from(selected).map((k) => splitKey(k).row_id),
                    ),
                  );
                  if (rowIds.length) onFixRows(rowIds, linkType);
                }}
                disabled={busy}
                className="rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-60"
              >
                {t("linkCheckRun.fixSelectedAi", {
                  n: new Set(
                    Array.from(selected).map((k) => splitKey(k).row_id),
                  ).size,
                })}
              </button>
            )}
            <button
              type="button"
              onClick={applyAction}
              disabled={busy}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              {view === "dismissed"
                ? t("linkCheckRun.restoreSelected", { n: selected.size })
                : t("linkCheckRun.dismissSelected", { n: selected.size })}
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {!error && (
        <>
          <div className="mt-3 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50 uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.colRow")}</th>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.rawLang")}</th>
                  <th className="px-3 py-2 font-medium">{t("linkCheckRun.rawOriginal")}</th>
                  <th className="px-3 py-2 font-medium">
                    <span className="inline-flex items-center gap-1.5">
                      {selectable && pageKeys.length > 0 && (
                        <input
                          type="checkbox"
                          checked={allSelected}
                          onChange={toggleAll}
                          title={t("linkCheckRun.selectAll")}
                          className="h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
                        />
                      )}
                      {t("linkCheckRun.rawTranslation")}
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody
                className={
                  "divide-y divide-neutral-100 dark:divide-neutral-800 " +
                  // Dim while a fetch is in flight so filter/page changes give
                  // immediate feedback (the recompute can take ~0.5s).
                  (loading ? "opacity-50 transition-opacity" : "")
                }
              >
                {loading && rows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-3 py-10 text-center">
                      <span className="inline-flex items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
                        <Spinner /> {t("common.loading")}
                      </span>
                    </td>
                  </tr>
                )}
                {discrepancyLinksOnly
                  ? rows.flatMap((r) => {
                      // One sub-row per problem link, so each wrong translation
                      // link lines up beside the original it was paired to.
                      const probs = r.translation.filter((l) => l.kind !== "ok");
                      return probs.map((l, idx) => {
                        const inView =
                          view === "dismissed" ? l.dismissed : !l.dismissed;
                        const showCheck = selectable && inView && !l.resolved;
                        const k = errKey(r.row_id, l.url);
                        return (
                          <tr key={`${r.row_id}:${l.url}`} className="align-top">
                            {idx === 0 && (
                              <td
                                rowSpan={probs.length}
                                className="px-3 py-2 tabular-nums text-neutral-500"
                              >
                                #{r.row_position + 1}
                              </td>
                            )}
                            {idx === 0 && (
                              <td
                                rowSpan={probs.length}
                                className="px-3 py-2 whitespace-nowrap font-medium text-neutral-700 dark:text-neutral-300"
                              >
                                {r.lang || "—"}
                              </td>
                            )}
                            <td className="px-3 py-2">
                              {l.original ? (
                                <Anchor
                                  href={l.original}
                                  cls="text-blue-600 dark:text-blue-400"
                                />
                              ) : (
                                <Dash />
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <span className="flex items-start gap-1.5">
                                {showCheck && (
                                  <input
                                    type="checkbox"
                                    checked={selected.has(k)}
                                    onChange={() => toggle(k)}
                                    className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-neutral-300 dark:border-neutral-600"
                                  />
                                )}
                                <span className="min-w-0">
                                  <TypeChip type={l.link_type} />
                                  <TranslationLink tag={l} />
                                </span>
                              </span>
                            </td>
                          </tr>
                        );
                      });
                    })
                  : rows.map((r) => (
                      <tr key={r.row_id} className="align-top">
                        <td className="px-3 py-2 tabular-nums text-neutral-500">
                          #{r.row_position + 1}
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap font-medium text-neutral-700 dark:text-neutral-300">
                          {r.lang || "—"}
                        </td>
                        <td className="px-3 py-2">
                          <PlainLinks links={r.original} cls="text-blue-600 dark:text-blue-400" />
                        </td>
                        <td className="px-3 py-2">
                          <TranslationCell
                            rowId={r.row_id}
                            links={r.translation}
                            view={view}
                            selectable={selectable}
                            selected={selected}
                            toggle={toggle}
                            onlyErrors={discrepancyLinksOnly}
                          />
                        </td>
                      </tr>
                    ))}
                {rows.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-3 py-4 text-center text-sm text-neutral-500 dark:text-neutral-400"
                    >
                      {view === "active"
                        ? t("linkCheckRun.rawTableEmptyDiscrepancies")
                        : view === "dismissed"
                          ? t("linkCheckRun.rawTableEmptyDismissed")
                          : view === "solved"
                            ? t("linkCheckRun.rawTableEmptySolved")
                            : t("linkCheckRun.rawTableEmpty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function Dash() {
  return <span className="text-neutral-300 dark:text-neutral-600">—</span>;
}

function Anchor({ href, cls }: { href: string; cls: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={"break-all hover:underline " + cls}
    >
      {href}
    </a>
  );
}

function PlainLinks({ links, cls }: { links: string[]; cls: string }) {
  if (links.length === 0) return <Dash />;
  return (
    <ul className="space-y-2">
      {links.map((l, i) => (
        <li key={`${l}:${i}`}>
          <Anchor href={l} cls={cls} />
        </li>
      ))}
    </ul>
  );
}

function TypeChip({ type }: { type?: LinkTypeCategory | null }) {
  const { t } = useT();
  if (!type) return null;
  const label =
    type === "product"
      ? t("linkCheckRun.rawTypeProduct")
      : type === "internal"
        ? t("linkCheckRun.rawTypeInternal")
        : t("linkCheckRun.rawTypeExternal");
  return (
    <span
      title={label}
      aria-label={label}
      className="mr-1 inline-flex shrink-0 translate-y-[2px] text-neutral-400 dark:text-neutral-500"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-3.5 w-3.5"
        aria-hidden="true"
      >
        {type === "product" ? (
          <>
            <circle cx="12" cy="12" r="10" />
            <path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8" />
            <path d="M12 18V6" />
          </>
        ) : type === "external" ? (
          <>
            <path d="M15 3h6v6" />
            <path d="M10 14 21 3" />
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          </>
        ) : (
          <>
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
          </>
        )}
      </svg>
    </span>
  );
}

/** A single translation link, color-coded by how it compares to expected. */
function TranslationLink({ tag }: { tag: TranslationLinkTag }) {
  const { t } = useT();
  const dim = tag.dismissed ? " opacity-50" : "";
  const expectedTitle =
    tag.kind === "discrepancy" && tag.expected
      ? t("linkCheckRun.rawExpectedTooltip", { url: tag.expected })
      : undefined;

  // A corrected link — struck through, with a ✓, so reviewers can see what a
  // fix/replace run already handled.
  if (tag.resolved) {
    return (
      <span className="inline-flex items-start gap-1">
        <span
          className="text-green-600 dark:text-green-400"
          title={t("linkFix.fixedBadge")}
        >
          ✓
        </span>
        <a
          href={tag.url}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-neutral-400 line-through dark:text-neutral-500"
        >
          {tag.url}
        </a>
      </span>
    );
  }

  if (
    tag.kind === "discrepancy" &&
    tag.expected &&
    sameHost(tag.expected, tag.url)
  ) {
    const segs = urlDiff(tag.expected, tag.url);
    if (segs.some((s) => s.kind !== "equal")) {
      return (
        <a
          href={tag.url}
          target="_blank"
          rel="noopener noreferrer"
          title={expectedTitle}
          className={"break-all " + NEUTRAL + dim}
        >
          {segs.map((s, i) =>
            s.kind === "equal" ? (
              <span key={i}>{s.text}</span>
            ) : s.kind === "del" ? (
              <span
                key={i}
                className="text-red-600 line-through dark:text-red-400"
              >
                {s.text}
              </span>
            ) : (
              <span
                key={i}
                className="font-medium text-red-600 underline decoration-2 underline-offset-2 dark:text-red-400"
              >
                {s.text}
              </span>
            ),
          )}
        </a>
      );
    }
  }

  return (
    <a
      href={tag.url}
      target="_blank"
      rel="noopener noreferrer"
      title={expectedTitle}
      className={"break-all hover:underline " + kindCls(tag.kind) + dim}
    >
      {tag.url}
    </a>
  );
}

/** The "Translation links" column: every translation link color-coded against
 *  expected, with the wrong ones carrying the dismiss/restore checkbox.
 *  ``onlyErrors`` hides the OK (green) links for a problem-focused view. */
function TranslationCell({
  rowId,
  links,
  view,
  selectable,
  selected,
  toggle,
  onlyErrors = false,
}: {
  rowId: number;
  links: TranslationLinkTag[];
  view: TView;
  selectable: boolean;
  selected: Set<string>;
  toggle: (k: string) => void;
  onlyErrors?: boolean;
}) {
  const shown = onlyErrors ? links.filter((l) => l.kind !== "ok") : links;
  if (shown.length === 0) return <Dash />;
  return (
    <ul className="space-y-2">
      {shown.map((l, i) => {
        const isError = l.kind !== "ok";
        const inView = view === "dismissed" ? l.dismissed : !l.dismissed;
        const showCheck = selectable && isError && inView && !l.resolved;
        const k = errKey(rowId, l.url);
        return (
          <li key={`${l.url}:${i}`} className="flex items-start gap-1.5">
            {showCheck && (
              <input
                type="checkbox"
                checked={selected.has(k)}
                onChange={() => toggle(k)}
                className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-neutral-300 dark:border-neutral-600"
              />
            )}
            <span className="min-w-0">
              <TypeChip type={l.link_type} />
              <TranslationLink tag={l} />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function LegendDot({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={"inline-block h-2 w-2 rounded-full " + cls} />
      {label}
    </span>
  );
}
