"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelLinkFixRun,
  getLinkFixRun,
  resumeLinkFixRun,
  revertLinkFixRun,
  type DiffSegment,
  type LinkFixCell,
  type LinkFixRunDetail,
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
      await revertLinkFixRun(run.id);
      await tick(page);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  const isActive = run?.status === "queued" || run?.status === "running";
  const reverted = !!run?.reverted_at;

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("linkCheck.title"),
            href: `/library/${tableId}/link-check`,
          },
          { label: run?.name ?? t("breadcrumb.fix", { id: rid }) },
        ]}
      />

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {run && (
        <>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
                {t("linkFixRun.title", { id: run.id })}
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
                  <button
                    type="button"
                    onClick={onResume}
                    disabled={busy !== ""}
                    className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                  >
                    {busy === "resume" ? t("common.loading") : t("linkCheckRun.resume")}
                  </button>
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

          {/* progress while running */}
          {isActive && (
            <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
              <p className="mb-1.5 text-xs text-neutral-600 dark:text-neutral-400">
                {t("linkFixRun.fixing", {
                  done: run.done + run.failed + run.skipped,
                  total: run.total,
                })}
              </p>
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

          {/* counters */}
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Counter label={t("linkFixRun.fixed")} value={run.done} accent="green" />
            <Counter label={t("linkFixRun.failed")} value={run.failed} accent="red" />
            <Counter label={t("linkFixRun.skipped")} value={run.skipped} accent="neutral" />
            <Counter label={t("linkFixRun.total")} value={run.total} accent="neutral" />
          </div>

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

function FixCellRow({ cell }: { cell: LinkFixCell }) {
  const { t } = useT();
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
        <span className={"font-medium " + stateCls}>
          {t(`linkFixRun.state.${cell.state}` as never)}
        </span>
        {cell.violations.map((v, i) => (
          <span
            key={i}
            className="rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
            title={v.link}
          >
            {t(`linkCheckRun.${v.problem}` as never)}
          </span>
        ))}
      </div>
      {cell.error && (
        <p className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {cell.error}
        </p>
      )}
      {cell.state === "done" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-400">
              {t("linkFixRun.before")}
            </p>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 p-2 text-xs text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
              <DiffText segments={cell.before_segments} side="before" />
            </pre>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wide text-neutral-400">
              {t("linkFixRun.after")}
            </p>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-neutral-50 p-2 text-xs text-neutral-700 dark:bg-neutral-900 dark:text-neutral-300">
              <DiffText segments={cell.after_segments} side="after" />
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

/** Renders diff segments: on the Before side changed spans are struck red
 *  (links being removed/changed); on the After side they're highlighted green
 *  (links added/changed). */
function DiffText({
  segments,
  side,
}: {
  segments: DiffSegment[];
  side: "before" | "after";
}) {
  if (!segments || segments.length === 0) return null;
  return (
    <>
      {segments.map((s, i) =>
        s.changed ? (
          <mark
            key={i}
            className={
              side === "before"
                ? "bg-red-100 text-red-800 line-through dark:bg-red-950/50 dark:text-red-300"
                : "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-200"
            }
          >
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
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
