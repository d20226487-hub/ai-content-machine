"use client";

import { useCallback, useEffect, useState } from "react";

import { useT } from "@/lib/i18n-context";
import {
  getTableGenHealth,
  type ColumnGenHealth,
  type TableGenHealth,
} from "@/lib/library";

type RetryMode = "failed" | "truncated";

interface Props {
  tableId: number;
  /** Bumped by the parent (run finished, retry enqueued) to force a refetch. */
  refreshKey: number;
  /** Open the generation queue pre-set to this mode + the affected columns. */
  onRetry: (mode: RetryMode, columnIds: number[]) => void;
}

/**
 * Table-wide notice that some cells need attention, shown above the grid.
 *
 * Surfaces the two problems the grid can retry — API failures and truncated
 * (cut-off) replies — and, crucially, *which columns* each one hit, so the
 * operator knows whether to reach for "Retry failed" or "Retry truncated" and
 * where. Counts are whole-table (the grid only holds one page), fetched from
 * `/gen-health`. Renders nothing when the table is clean, still loading, or the
 * fetch failed — it's a supplementary hint, never a blocker.
 */
export function GenerationErrorBanner({ tableId, refreshKey, onRetry }: Props) {
  const { t } = useT();
  const [health, setHealth] = useState<TableGenHealth | null>(null);

  const load = useCallback(async () => {
    try {
      setHealth(await getTableGenHealth(tableId));
    } catch {
      // Best-effort: a failed health probe shouldn't spam the editor. Drop the
      // banner rather than show a scary error for a purely advisory widget.
      setHealth(null);
    }
  }, [tableId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (!health || (health.failed === 0 && health.truncated === 0)) return null;

  const failedCols = health.columns.filter((c) => c.failed > 0);
  const truncatedCols = health.columns.filter((c) => c.truncated > 0);

  return (
    <div className="mb-3 space-y-2" role="status">
      {health.failed > 0 && (
        <ProblemRow
          tone="failed"
          icon="✗"
          title={t("genErrors.failedTitle", { count: health.failed })}
          columnsLabel={t("genErrors.affectedColumns")}
          columns={failedCols}
          countOf={(c) => c.failed}
          retryLabel={t("genErrors.retryFailed", { count: health.failed })}
          retryHint={t("genErrors.retryFailedHint")}
          onRetry={() => onRetry("failed", failedCols.map((c) => c.column_id))}
        />
      )}
      {health.truncated > 0 && (
        <ProblemRow
          tone="truncated"
          icon="⚠"
          title={t("genErrors.truncatedTitle", { count: health.truncated })}
          hint={t("genErrors.truncatedHelp")}
          columnsLabel={t("genErrors.affectedColumns")}
          columns={truncatedCols}
          countOf={(c) => c.truncated}
          retryLabel={t("genErrors.retryTruncated", { count: health.truncated })}
          retryHint={t("genErrors.retryTruncatedHint")}
          onRetry={() =>
            onRetry("truncated", truncatedCols.map((c) => c.column_id))
          }
        />
      )}
    </div>
  );
}

function ProblemRow({
  tone,
  icon,
  title,
  hint,
  columnsLabel,
  columns,
  countOf,
  retryLabel,
  retryHint,
  onRetry,
}: {
  tone: "failed" | "truncated";
  icon: string;
  title: string;
  hint?: string;
  columnsLabel: string;
  columns: ColumnGenHealth[];
  countOf: (c: ColumnGenHealth) => number;
  retryLabel: string;
  retryHint: string;
  onRetry: () => void;
}) {
  // Red = hard failure (request errored); amber = truncation (partial kept).
  // Mirrors the per-cell cell colours in the grid so the two read as the same
  // signal at table scope.
  const box =
    tone === "failed"
      ? "border-red-200 bg-red-50 dark:border-red-900/50 dark:bg-red-950/30"
      : "border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/30";
  const titleColor =
    tone === "failed"
      ? "text-red-800 dark:text-red-200"
      : "text-amber-900 dark:text-amber-200";
  const bodyColor =
    tone === "failed"
      ? "text-red-700 dark:text-red-300"
      : "text-amber-800 dark:text-amber-300";
  const btn =
    tone === "failed"
      ? "border-red-300 text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-200 dark:hover:bg-red-900/40"
      : "border-amber-300 text-amber-800 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-200 dark:hover:bg-amber-900/40";

  return (
    <div
      className={
        "flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border px-3 py-2 text-sm " +
        box
      }
    >
      <span className={"font-medium " + titleColor}>
        <span aria-hidden className="mr-1.5">
          {icon}
        </span>
        {title}
      </span>

      <span className={"text-xs " + bodyColor}>
        <span className="opacity-70">{columnsLabel} </span>
        {columns.map((c, i) => (
          <span key={c.column_id}>
            {i > 0 && ", "}
            <span className="font-medium">{c.column_name}</span>
            <span className="opacity-70"> ({countOf(c)})</span>
          </span>
        ))}
      </span>

      {hint && (
        <span className={"w-full text-xs opacity-80 " + bodyColor}>{hint}</span>
      )}

      <button
        type="button"
        onClick={onRetry}
        title={retryHint}
        className={
          "ml-auto shrink-0 rounded-md border bg-white/60 px-3 py-1 text-xs font-medium dark:bg-transparent " +
          btn
        }
      >
        {retryLabel}
      </button>
    </div>
  );
}
