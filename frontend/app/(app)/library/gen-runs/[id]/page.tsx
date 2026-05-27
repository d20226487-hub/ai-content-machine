"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelGenerationRun,
  getGenerationRun,
  type BulkGenerationRunDetail,
} from "@/lib/library";

/**
 * Detail page for one bulk-generation run.
 *
 * Polls ``GET /library/gen-runs/{id}`` every ~2 seconds while the run
 * is active (queued / running), stops polling on any terminal status.
 * Provides a Cancel button for active runs and a link back to the
 * source table for finished ones.
 *
 * The progress visualisation reuses the same numbers as the inline
 * banner in the editor — operators flip between the two surfaces
 * during a long batch.
 */
export default function GenerationRunDetailPage({
  params,
}: {
  // Next 15 typed route params arrive as a Promise.
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const runId = Number(id);
  const { t } = useT();
  const [run, setRun] = useState<BulkGenerationRunDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const stoppedRef = useRef(false);

  const tick = useCallback(async () => {
    try {
      const r = await getGenerationRun(runId);
      setRun(r);
      setLoadError(null);
      // Terminal: stop polling. The next tick won't be scheduled.
      if (r.status === "done" || r.status === "cancelled" || r.status === "failed") {
        stoppedRef.current = true;
      }
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    }
  }, [runId]);

  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setLoadError("Invalid run id");
      return;
    }
    stoppedRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick();
      if (cancelled || stoppedRef.current) return;
      timer = setTimeout(loop, 2000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId, tick]);

  async function onCancel() {
    if (run == null || cancelling) return;
    if (!window.confirm(t("genRun.cancelConfirm"))) return;
    setCancelling(true);
    try {
      await cancelGenerationRun(run.id);
      // Force one immediate tick so the status pill updates without
      // waiting for the next 2s cycle.
      stoppedRef.current = false;
      await tick();
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={run ? `/library/${run.table_id}` : "/library"}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("genRun.backToTable")}
        </Link>
      </div>

      {loadError && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {run && <RunBody run={run} cancelling={cancelling} onCancel={onCancel} />}
    </main>
  );
}

function RunBody({
  run,
  cancelling,
  onCancel,
}: {
  run: BulkGenerationRunDetail;
  cancelling: boolean;
  onCancel: () => void;
}) {
  const { t } = useT();
  const accounted = run.done + run.failed + run.skipped;
  const pct = run.total > 0 ? Math.min(100, Math.round((accounted / run.total) * 100)) : 0;
  const isActive = run.status === "queued" || run.status === "running";
  const elapsedMs =
    run.started_at && run.finished_at
      ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
      : run.started_at
        ? Date.now() - new Date(run.started_at).getTime()
        : null;

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("genRun.title", { id: run.id })}
          </h1>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("genRun.meta", {
              by: run.created_by_name ?? "—",
              when: new Date(run.created_at).toLocaleString(),
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={run.status} />
          {isActive && (
            <button
              type="button"
              onClick={onCancel}
              disabled={cancelling}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
            >
              {cancelling ? t("common.loading") : t("genRun.cancel")}
            </button>
          )}
        </div>
      </header>

      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 text-sm">
          <p className="font-medium text-neutral-900 dark:text-neutral-100">
            {t("genRun.counters", {
              done: run.done,
              total: run.total,
            })}
          </p>
          <p className="tabular-nums text-neutral-600 dark:text-neutral-400">
            {pct}%
          </p>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
          <div
            className={
              "h-full transition-[width] duration-300 ease-out " +
              (run.status === "failed"
                ? "bg-red-500"
                : run.status === "cancelled"
                  ? "bg-neutral-400 dark:bg-neutral-500"
                  : "bg-blue-500 dark:bg-blue-400")
            }
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-4 text-xs">
          <CounterCell label={t("genRun.colDone")} value={run.done} accent="green" />
          <CounterCell label={t("genRun.colFailed")} value={run.failed} accent="red" />
          <CounterCell label={t("genRun.colSkipped")} value={run.skipped} accent="neutral" />
        </div>
        {elapsedMs != null && (
          <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
            {t("genRun.elapsed", {
              elapsed: formatDuration(elapsedMs),
            })}
            {run.started_at && ` · ${new Date(run.started_at).toLocaleString()}`}
            {run.finished_at && ` → ${new Date(run.finished_at).toLocaleString()}`}
          </p>
        )}
        {run.error && (
          <pre className="mt-3 whitespace-pre-wrap rounded-md bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-300">
            {run.error}
          </pre>
        )}
      </section>
    </>
  );
}

function CounterCell({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "green" | "red" | "neutral";
}) {
  const cls =
    accent === "green"
      ? "text-green-700 dark:text-green-400"
      : accent === "red"
        ? "text-red-700 dark:text-red-400"
        : "text-neutral-700 dark:text-neutral-300";
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className={"mt-0.5 text-lg font-semibold tabular-nums " + cls}>{value}</p>
    </div>
  );
}

function StatusPill({ status }: { status: BulkGenerationRunDetail["status"] }) {
  const { t } = useT();
  const cls =
    status === "running" || status === "queued"
      ? "bg-blue-50 text-blue-800 ring-blue-300 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-500/30"
      : status === "done"
        ? "bg-green-50 text-green-800 ring-green-300 dark:bg-green-950/40 dark:text-green-300 dark:ring-green-500/30"
        : status === "cancelled"
          ? "bg-neutral-100 text-neutral-700 ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600"
          : "bg-red-50 text-red-800 ring-red-300 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-500/30";
  const label =
    status === "queued"
      ? t("genRun.statusQueued")
      : status === "running"
        ? t("genRun.statusRunning")
        : status === "done"
          ? t("genRun.statusDone")
          : status === "cancelled"
            ? t("genRun.statusCancelled")
            : t("genRun.statusFailed");
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-3 py-0.5 text-xs font-medium ring-1 ring-inset " +
        cls
      }
    >
      {label}
    </span>
  );
}

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m}m ${rs}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${rm}m`;
}
