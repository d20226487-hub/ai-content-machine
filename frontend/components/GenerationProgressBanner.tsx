"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelGenerationRun,
  getActiveGenerationRun,
  type BulkGenerationRun,
} from "@/lib/library";

/**
 * Inline progress banner for an active bulk-generation run.
 *
 * Mounted by the table editor. Polls
 * ``GET /library/tables/{id}/active-gen-run`` every couple of seconds
 * while the run is alive (queued / running), stops polling on any
 * terminal status. On render:
 *   * Shows a progress bar (% = done / total) + counter line.
 *   * "Cancel" button POSTs the cancel endpoint — workers see
 *     status='cancelled' and short-circuit subsequent cells.
 *   * "Details →" link opens the detail page.
 *
 * Notifies the parent (via ``onRunFinished``) when polling sees a
 * terminal status — useful for refreshing the cell grid so the
 * finalized statuses paint in.
 *
 * Hidden entirely when there's no active run for this table.
 */
export function GenerationProgressBanner({
  tableId,
  onRunFinished,
}: {
  tableId: number;
  /** Fires once when polling observes a terminal status. */
  onRunFinished?: (run: BulkGenerationRun) => void;
}) {
  const { t } = useT();
  const [run, setRun] = useState<BulkGenerationRun | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef<number | null>(null);

  const tick = useCallback(async () => {
    try {
      const r = await getActiveGenerationRun(tableId);
      setRun(r);
      // First-time observation of a terminal status: notify parent.
      // We dedupe by run id so a fast-polling tick that re-fires while
      // the run still shows doesn't call onRunFinished multiple times.
      if (
        r != null &&
        (r.status === "done" || r.status === "cancelled" || r.status === "failed")
      ) {
        if (finishedRef.current !== r.id) {
          finishedRef.current = r.id;
          onRunFinished?.(r);
        }
      }
    } catch (e) {
      // Silent — banner stays in its last visible state. The polling
      // loop retries; transient API errors during a worker restart
      // shouldn't make the banner blink red.
      if (e instanceof ApiError) {
        setError(e.message);
      }
    }
  }, [tableId, onRunFinished]);

  // Polling loop: 2s while active, paused otherwise. Active is
  // queued/running. The empty "no active run" state ALSO polls
  // (slower, 5s) so a fresh run started elsewhere shows up here.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick();
      if (cancelled) return;
      const isActive =
        run != null && (run.status === "queued" || run.status === "running");
      timer = setTimeout(loop, isActive ? 2000 : 5000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // run.status is intentionally in the deps via `run` — when the
    // status changes we re-schedule with the new cadence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tableId, run?.status]);

  if (run == null) return null;

  // Show the banner only while the run is meaningfully in flight or
  // recently terminal (so the user gets a final "Done" / "Cancelled"
  // glimpse). We hide it on the NEXT poll after terminal — the parent
  // will have refreshed the cell grid by then via onRunFinished.
  // For "recently terminal" we just keep showing until polling sees
  // active-run = null (the API returns null for terminal runs).
  // This branch is structurally unreachable because the API only
  // returns active runs, but render defensively anyway.
  const isActive = run.status === "queued" || run.status === "running";
  if (!isActive) return null;

  const pct =
    run.total > 0
      ? Math.min(
          100,
          Math.round(((run.done + run.failed + run.skipped) / run.total) * 100),
        )
      : 0;

  async function onCancel() {
    if (run == null || cancelling) return;
    if (!window.confirm(t("genBanner.cancelConfirm"))) return;
    setCancelling(true);
    setError(null);
    try {
      const updated = await cancelGenerationRun(run.id);
      setRun(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <section
      role="status"
      aria-live="polite"
      className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-100"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-medium">
          {t("genBanner.generating", {
            done: run.done,
            total: run.total,
          })}
        </span>
        {run.failed > 0 && (
          <span className="text-red-700 dark:text-red-300">
            {t("genBanner.failedCount", { n: run.failed })}
          </span>
        )}
        {run.skipped > 0 && (
          <span className="text-neutral-600 dark:text-neutral-400">
            {t("genBanner.skippedCount", { n: run.skipped })}
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          <Link
            href={`/library/gen-runs/${run.id}`}
            className="text-xs font-medium text-blue-700 underline-offset-2 hover:underline dark:text-blue-300"
          >
            {t("genBanner.details")}
          </Link>
          <button
            type="button"
            onClick={() => void onCancel()}
            disabled={cancelling}
            className="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
          >
            {cancelling ? t("common.loading") : t("genBanner.cancel")}
          </button>
        </span>
      </div>
      {/* Progress bar — pure CSS, the % is on the inner div's width. */}
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-blue-100 dark:bg-blue-950/60">
        <div
          className="h-full bg-blue-500 transition-[width] duration-300 ease-out dark:bg-blue-400"
          style={{ width: `${pct}%` }}
        />
      </div>
      {error != null && (
        <p className="mt-1 text-xs text-red-700 dark:text-red-300">{error}</p>
      )}
    </section>
  );
}
