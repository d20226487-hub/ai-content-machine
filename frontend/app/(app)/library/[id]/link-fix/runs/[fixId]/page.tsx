"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { Spinner } from "@/components/Spinner";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelLinkFixRun,
  getLinkFixRun,
  resumeLinkFixRun,
  revertLinkFixRun,
  type DiffBlock,
  type LinkFixCell,
  type LinkFixRunDetail,
  type LinkFixViolationLite,
} from "@/lib/linkFix";

const PAGE_SIZE = 25;

export default function LinkFixRunPage({
  params,
}: {
  params: Promise<{ id: string; fixId: string }>;
}) {
  const { id, fixId } = use(params);
  const tableId = Number(id);
  const rid = Number(fixId);
  const { t } = useT();

  const [run, setRun] = useState<LinkFixRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "cancel" | "resume" | "revert">("");
  const [revertNotice, setRevertNotice] = useState<string | null>(null);
  const stoppedRef = useRef(false);

  const tick = useCallback(
    async (p: number) => {
      try {
        const r = await getLinkFixRun(rid, p, PAGE_SIZE);
        setRun(r);
        setError(null);
        // Keep polling while the fix is active OR while its auto re-check is
        // still in flight (recheck_run_id appears only after the fix is done).
        if (r.status === "done" || r.status === "cancelled" || r.status === "failed") {
          stoppedRef.current = true;
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        stoppedRef.current = true;
      }
    },
    [rid],
  );

  useEffect(() => {
    if (!Number.isFinite(rid)) return;
    stoppedRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick(page);
      if (cancelled || stoppedRef.current) return;
      timer = setTimeout(loop, 2000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [rid, page, tick]);

  async function onCancel() {
    if (!run) return;
    if (!window.confirm(t("linkFixRun.confirmCancel"))) return;
    setBusy("cancel");
    try {
      await cancelLinkFixRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function onResume() {
    if (!run) return;
    setBusy("resume");
    try {
      await resumeLinkFixRun(run.id);
      stoppedRef.current = false;
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function onRevert() {
    if (!run) return;
    if (!window.confirm(t("linkFixRun.confirmRevert"))) return;
    setBusy("revert");
    try {
      const res = await revertLinkFixRun(run.id);
      setRevertNotice(
        res.skipped_count > 0
          ? t("linkFixRun.revertSkippedNote", {
              reverted: res.reverted_count,
              skipped: res.skipped_count,
            })
          : null,
      );
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  const isActive = run?.status === "queued" || run?.status === "running";
  const reverted = !!run?.reverted_at;
  // A running job that hasn't made progress for a while is effectively stalled
  // (worker died / lost message). Only then do we offer Resume — a healthy
  // running job is left to finish on its own. 90s comfortably clears a slow
  // per-cell LLM call without leaving a truly-stuck job without a way out.
  const STALL_MS = 90_000;
  const stalled =
    run?.status === "running" &&
    !!run.last_progress_at &&
    Date.now() - new Date(run.last_progress_at).getTime() > STALL_MS;

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("linkCheck.title"),
            href: `/library/${tableId}/link-check`,
          },
          {
            label:
              run?.name ??
              t(
                run?.method === "replace"
                  ? "breadcrumb.replace"
                  : run?.method === "strip"
                    ? "breadcrumb.strip"
                    : "breadcrumb.fix",
                { id: rid },
              ),
          },
        ]}
      />

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {!run && !error && (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-neutral-500 dark:text-neutral-400">
          <Spinner /> {t("common.loading")}
        </div>
      )}

      {run && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {t(
                  run.method === "replace"
                    ? "linkFixRun.replaceTitle"
                    : run.method === "strip"
                      ? "linkFixRun.stripTitle"
                      : "linkFixRun.title",
                  { id: run.id },
                )}
              </h1>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("linkCheckRun.meta", {
                  by: run.created_by_name ?? "—",
                  when: new Date(run.created_at).toLocaleString(),
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <LinkCheckStatusChip status={run.status} />
              {isActive && (
                <>
                  {stalled && (
                    <button
                      type="button"
                      onClick={onResume}
                      disabled={busy !== ""}
                      title={t("linkFixRun.resumeStalledHint")}
                      className="rounded-md border border-amber-300 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-60 dark:border-amber-700/60 dark:text-amber-300 dark:hover:bg-amber-900/20"
                    >
                      {busy === "resume" ? t("common.loading") : t("linkCheckRun.resume")}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={onCancel}
                    disabled={busy !== ""}
                    className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                  >
                    {busy === "cancel" ? t("common.loading") : t("linkCheckRun.cancel")}
                  </button>
                </>
              )}
              {!isActive && run.done > 0 && !reverted && (
                <button
                  type="button"
                  onClick={onRevert}
                  disabled={busy !== ""}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                >
                  {busy === "revert" ? t("common.loading") : t("linkFixRun.revert")}
                </button>
              )}
            </div>
          </header>

          {reverted && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-400/10 dark:text-amber-200">
              {t("linkFixRun.revertedNote", {
                when: new Date(run.reverted_at as string).toLocaleString(),
              })}
            </p>
          )}

          {revertNotice && (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900 ring-1 ring-inset ring-amber-200 dark:bg-amber-400/10 dark:text-amber-200 dark:ring-amber-400/25">
              {revertNotice}
            </p>
          )}

          {/* progress while running */}
          {isActive && (
            <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                {t("linkFixRun.fixing", {
                  done: run.done + run.failed + run.skipped,
                  total: run.total,
                })}
              </p>
              {stalled && (
                <p className="mb-1.5 text-xs text-amber-700 dark:text-amber-300">
                  {t("linkFixRun.stalledNote")}
                </p>
              )}
              <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
                <div
                  className="h-full bg-violet-500 transition-[width] duration-300 dark:bg-violet-400"
                  style={{
                    width: `${
                      run.total > 0
                        ? Math.round(
                            ((run.done + run.failed + run.skipped) / run.total) * 100,
                          )
                        : 5
                    }%`,
                  }}
                />
              </div>
            </div>
          )}

          {/* counters — these count CELLS (one per row). For replace runs a
              note below bridges to the link count the user actually selected. */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Counter label={t("linkFixRun.fixed")} value={run.done} accent="green" />
            <Counter label={t("linkFixRun.failed")} value={run.failed} accent="red" />
            <Counter label={t("linkFixRun.skipped")} value={run.skipped} accent="neutral" />
            <Counter label={t("linkFixRun.total")} value={run.total} accent="neutral" />
          </div>
          {(run.method === "replace" || run.method === "strip") &&
            run.links_changed != null && (
              <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-300">
                {t(
                  run.method === "strip"
                    ? "linkFixRun.linksStrippedNote"
                    : "linkFixRun.linksReplacedNote",
                  {
                    links: run.links_changed,
                    cells: run.done,
                  },
                )}
              </p>
            )}

          {/* The fix re-verifies in place — point the user back to the source
              check run to see what's now Solved / Unsolved. */}
          {run.source_run_id && run.status === "done" && (
            <p className="mt-3 text-sm">
              <Link
                href={`/library/${tableId}/link-check/runs/${run.source_run_id}`}
                className="text-violet-700 hover:underline dark:text-violet-300"
              >
                {t("linkFixRun.viewRecheck")}
              </Link>
            </p>
          )}

          {/* per-cell before/after */}
          {run.total_cells > 0 && (
            <>
              <div className="mt-5 space-y-3">
                {run.items.map((c) => (
                  <FixCellRow key={`${c.row_id}:${c.column_id}`} cell={c} />
                ))}
              </div>
              <Pagination
                page={run.page}
                pageSize={run.page_size}
                total={run.total_cells}
                onPage={setPage}
              />
            </>
          )}
        </>
      )}
    </main>
  );
}

/** Collapse a cell's violations to one entry per distinct problem type (order
 *  preserved), carrying the count and the underlying links for the tooltip. */
function dedupeViolations(
  violations: LinkFixViolationLite[],
): { problem: string; count: number; links: string[] }[] {
  const order: string[] = [];
  const by = new Map<string, { count: number; links: string[] }>();
  for (const v of violations) {
    let e = by.get(v.problem);
    if (!e) {
      e = { count: 0, links: [] };
      by.set(v.problem, e);
      order.push(v.problem);
    }
    e.count += 1;
    if (v.link) e.links.push(v.link);
  }
  return order.map((problem) => ({ problem, ...by.get(problem)! }));
}

function FixCellRow({ cell }: { cell: LinkFixCell }) {
  const { t } = useT();
  const [showFull, setShowFull] = useState(false);
  const stateCls =
    cell.state === "done"
      ? "text-green-700 dark:text-green-400"
      : cell.state === "failed"
        ? "text-red-700 dark:text-red-400"
        : cell.state === "skipped"
          ? "text-neutral-500 dark:text-neutral-400"
          : "text-amber-700 dark:text-amber-300";
  return (
    <div className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium text-neutral-700 dark:text-neutral-300">
          {cell.column_name} · #{cell.row_position + 1}
        </span>
        {/* For a done cell the "Исправлено" label lives on the corrected-link
            box below; in the header it'd float free of the change it describes.
            Other states (failed / skipped / pending) have no box, so keep them
            here. */}
        {cell.state !== "done" && (
          <span className={"font-medium " + stateCls}>
            {t(`linkFixRun.state.${cell.state}` as never)}
          </span>
        )}
        {/* Dedupe by problem type: a translation cell can carry several
            omitted + hallucinated links (two halves of each wrong link), which
            rendered as a noisy, misleading repeat of the same two labels. Show
            one chip per distinct problem, with a count when it stands for more
            than one link. */}
        {dedupeViolations(cell.violations).map(({ problem, count, links }) => (
          <span
            key={problem}
            className="rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
            title={links.join("\n")}
          >
            {t(`linkCheckRun.${problem}` as never)}
            {count > 1 ? ` ×${count}` : ""}
          </span>
        ))}
      </div>
      {cell.error && (
        <p className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {cell.error}
        </p>
      )}
      {cell.state === "done" &&
        (() => {
          // ONE aligned snippet drives BOTH panes — changed spans + a little
          // context, the same unchanged stretches collapsed on each side — so
          // the Before/After snippets stay lined up (a pure deletion no longer
          // snippets one pane while leaving the other whole).
          const snip = buildSnippet(cell.diff_blocks);
          const trimmed = snip.trimmed;
          const items = showFull ? cell.diff_blocks : snip.items;
          return (
            <>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-400">
                    {t("linkFixRun.before")}
                  </p>
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 p-2 text-xs text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
                    <DiffText items={items} side="before" />
                  </pre>
                </div>
                <div>
                  <p className="mb-1 flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wide text-neutral-400">
                      {t("linkFixRun.after")}
                    </span>
                    <span className="rounded-full bg-green-50 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-950/40 dark:text-green-400">
                      {t("linkFixRun.state.done")}
                    </span>
                  </p>
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 p-2 text-xs text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
                    <DiffText items={items} side="after" />
                  </pre>
                </div>
              </div>
              {trimmed && (
                <button
                  type="button"
                  onClick={() => setShowFull((v) => !v)}
                  className="mt-1.5 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {showFull
                    ? t("linkFixRun.showSnippet")
                    : t("linkFixRun.showFull")}
                </button>
              )}
            </>
          );
        })()}
    </div>
  );
}

/** A snippet render item: an aligned diff block, or a collapsed gap. */
type RenderItem = DiffBlock | { ellipsis: true };

/** Chars of unchanged context kept on each side of a changed span. */
const SNIPPET_CONTEXT = 60;

/** Reduce an aligned diff to just its changed blocks plus a little surrounding
 *  context, collapsing long unchanged stretches to an ellipsis — so a one-link
 *  edit inside a large cell reads as a focused snippet, not the whole document.
 *  Operating on the SHARED block list (not the two panes independently) keeps
 *  the Before/After snippets aligned. `trimmed` reports whether anything was
 *  collapsed (drives the "show full" toggle). Blocks alternate changed/unchanged
 *  (the backend coalesces runs), so each unchanged run is trimmed by its changed
 *  neighbours; an unchanged block has `before === after`. */
function buildSnippet(blocks: DiffBlock[]): {
  items: RenderItem[];
  trimmed: boolean;
} {
  if (!blocks.some((b) => b.changed)) return { items: blocks, trimmed: false };
  const items: RenderItem[] = [];
  let trimmed = false;
  const gap = () => {
    const last = items[items.length - 1];
    if (last && "ellipsis" in last) return;
    items.push({ ellipsis: true });
    trimmed = true;
  };
  const keep = (text: string): DiffBlock => ({
    before: text,
    after: text,
    changed: false,
  });
  const n = blocks.length;
  for (let i = 0; i < n; i++) {
    const b = blocks[i];
    if (b.changed) {
      items.push(b);
      continue;
    }
    const prevChanged = i > 0 && blocks[i - 1].changed;
    const nextChanged = i < n - 1 && blocks[i + 1].changed;
    const text = b.before; // unchanged → before === after
    if (prevChanged && nextChanged) {
      if (text.length <= SNIPPET_CONTEXT * 2) items.push(b);
      else {
        items.push(keep(text.slice(0, SNIPPET_CONTEXT)));
        gap();
        items.push(keep(text.slice(-SNIPPET_CONTEXT)));
      }
    } else if (prevChanged) {
      if (text.length <= SNIPPET_CONTEXT) items.push(b);
      else {
        items.push(keep(text.slice(0, SNIPPET_CONTEXT)));
        gap();
      }
    } else if (nextChanged) {
      if (text.length <= SNIPPET_CONTEXT) items.push(b);
      else {
        gap();
        items.push(keep(text.slice(-SNIPPET_CONTEXT)));
      }
    } else {
      gap(); // unchanged and far from any change → collapse entirely
    }
  }
  return { items, trimmed };
}

/** Renders one pane of the aligned diff. `side` selects the block's before/
 *  after text: changed spans are struck red on Before, highlighted green on
 *  After; a block empty on this side (a pure insert/delete) renders nothing;
 *  collapsed gaps render as a centered ellipsis. Both panes pass the SAME items
 *  so they line up. */
function DiffText({
  items,
  side,
}: {
  items: RenderItem[];
  side: "before" | "after";
}) {
  if (!items || items.length === 0) return null;
  return (
    <>
      {items.map((it, i) => {
        if ("ellipsis" in it) {
          return (
            <span
              key={i}
              className="my-0.5 block select-none text-center text-neutral-400 dark:text-neutral-500"
            >
              ⋯
            </span>
          );
        }
        const text = side === "before" ? it.before : it.after;
        if (!text) return null;
        return it.changed ? (
          <mark
            key={i}
            className={
              side === "before"
                ? "bg-red-100 text-red-800 line-through dark:bg-red-950/50 dark:text-red-300"
                : "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-200"
            }
          >
            {text}
          </mark>
        ) : (
          <span key={i}>{text}</span>
        );
      })}
    </>
  );
}

function Counter({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "red" | "green" | "neutral";
}) {
  const cls =
    accent === "red"
      ? "text-red-700 dark:text-red-400"
      : accent === "green"
        ? "text-green-700 dark:text-green-400"
        : "text-neutral-700 dark:text-neutral-300";
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900">
      <p className="text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className={"mt-0.5 text-lg font-semibold tabular-nums " + cls}>{value}</p>
    </div>
  );
}
