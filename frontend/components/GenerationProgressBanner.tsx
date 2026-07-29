"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelGenerationRun,
  getActiveGenerationRun,
  recoverGenerationRun,
  type BulkGenerationRun,
} from "@/lib/library";

// A run whose settled-cell count hasn't advanced for this long looks frozen —
// that's when the Recover button appears. Matches the backend's recover grace
// (_RECOVER_GRACE_MINUTES), so a visible button corresponds to a backend that
// will actually act rather than no-op.
const STALL_MS = 120_000;

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
  const [recovering, setRecovering] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef<number | null>(null);
  // Stall clock for the *currently active* run. `since` marks when the settled
  // count last advanced; it's reset whenever the count moves, whenever a
  // different run appears, and whenever there's no active run — so a count that
  // then sits still past STALL_MS distinguishes a frozen run from a merely slow
  // one and surfaces the Recover button. `runId` scopes the clock to one run so
  // idle dwell time before the user clicks Generate can't leak in (see tick()).
  const progressRef = useRef<{ runId: number; value: number; since: number }>({
    runId: -1,
    value: -1,
    since: 0,
  });

  const tick = useCallback(async () => {
    try {
      const r = await getActiveGenerationRun(tableId);
      setRun(r);
      // Stall tracking: the clock runs only while a single active run is in
      // flight. Reset `since` when there's no run, when a *different* run
      // appears (null→running, or one run to the next), or when the settled
      // count advances. This keeps idle dwell time before Generate — and a
      // previous run's staleness — from leaking into a fresh run and firing a
      // bogus Recover button. A count that then sits still past STALL_MS is
      // what genuinely surfaces the Recover button.
      if (r == null) {
        progressRef.current = { runId: -1, value: -1, since: 0 };
      } else {
        const prog = r.done + r.failed + r.skipped;
        if (
          r.id !== progressRef.current.runId ||
          prog !== progressRef.current.value
        ) {
          progressRef.current = { runId: r.id, value: prog, since: Date.now() };
        }
      }
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

  const settled = run.done + run.failed + run.skipped;
  const pct = run.total > 0 ? Math.min(100, Math.round((settled / run.total) * 100)) : 0;

  // Frozen-run heuristic: settled count static past STALL_MS and not yet
  // complete. Date.now() re-evaluates each ~2s poll (setRun re-renders), so the
  // Recover button appears within a tick of crossing the threshold.
  const looksStuck =
    settled < run.total &&
    progressRef.current.since > 0 &&
    Date.now() - progressRef.current.since > STALL_MS;

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

  async function onRecover() {
    if (run == null || recovering) return;
    setRecovering(true);
    setNotice(null);
    setError(null);
    try {
      const before = run.failed;
      const updated = await recoverGenerationRun(run.id);
      setRun(updated);
      // Recovered cells are counted as failures, so the delta is how many the
      // reconcile unstuck. Zero means the run was still producing cells (the
      // grace refused it) or nothing was wedged.
      const recovered = Math.max(0, updated.failed - before);
      setNotice(
        recovered > 0
          ? t("genBanner.recovered", { n: recovered })
          : t("genBanner.recoverNoop"),
      );
      // Reset the stall clock so the button hides until the run stalls again.
      progressRef.current = {
        runId: updated.id,
        value: updated.done + updated.failed + updated.skipped,
        since: Date.now(),
      };
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
    } finally {
      setRecovering(false);
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
          {looksStuck && (
            <button
              type="button"
              onClick={() => void onRecover()}
              disabled={recovering}
              title={t("genBanner.recoverTitle")}
              className="rounded-md border border-amber-400 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60 dark:border-amber-600/60 dark:bg-amber-950/40 dark:text-amber-200"
            >
              {recovering ? t("common.loading") : t("genBanner.recover")}
            </button>
          )}
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
      {notice != null && (
        <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">{notice}</p>
      )}
    </section>
  );
}
