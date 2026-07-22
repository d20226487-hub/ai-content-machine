"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTableCost, type TableCost } from "@/lib/library";
import { formatUsd } from "@/lib/spend";

/**
 * Cumulative generation spend for a table, expandable to a per-column
 * breakdown.
 *
 * Collapsed by default and fetched only when opened — the aggregate runs over
 * usage_events, which grows by a row per LLM call, so it shouldn't be paid on
 * every table page load.
 */
export function TableCostPanel({ tableId }: { tableId: number }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [cost, setCost] = useState<TableCost | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCost(await getTableCost(tableId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    } finally {
      setLoading(false);
    }
  }, [tableId, t]);

  useEffect(() => {
    if (open && cost === null && !loading) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div className="mt-4 rounded-lg border border-neutral-200 dark:border-neutral-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
          {t("tableCost.title")}
        </span>
        <span className="flex items-center gap-3">
          {cost && (
            <span className="tabular-nums text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              {formatUsd(cost.cost_usd)}
            </span>
          )}
          <span className="text-xs text-neutral-400">{open ? "▲" : "▼"}</span>
        </span>
      </button>

      {open && (
        <div className="border-t border-neutral-200 px-4 py-3 dark:border-neutral-800">
          {loading && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {t("common.loading")}
            </p>
          )}
          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </p>
          )}

          {cost && !loading && (
            <>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("tableCost.summary", {
                  usd: formatUsd(cost.cost_usd),
                  gens: cost.generations,
                  cells: cost.cells,
                })}
              </p>
              {/* A regenerated cell bills twice but is still one cell, so
                  generations > cells is expected, not a bug. */}
              {cost.generations > cost.cells && (
                <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                  {t("tableCost.includesRegenerations")}
                </p>
              )}
              {cost.unpriced_generations > 0 && (
                <p className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                  {t("tableCost.unpricedWarning", {
                    n: cost.unpriced_generations,
                  })}
                </p>
              )}

              {cost.columns.length > 0 ? (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-neutral-500 dark:text-neutral-400">
                        <th className="pb-1 pr-4 font-medium">
                          {t("tableCost.colColumn")}
                        </th>
                        <th className="pb-1 pr-4 text-right font-medium">
                          {t("tableCost.colCost")}
                        </th>
                        <th className="pb-1 pr-4 text-right font-medium">
                          {t("tableCost.colCells")}
                        </th>
                        <th className="pb-1 pr-4 text-right font-medium">
                          {t("tableCost.colGenerations")}
                        </th>
                        <th className="pb-1 text-right font-medium">
                          {t("tableCost.colTokens")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="text-neutral-800 dark:text-neutral-200">
                      {cost.columns.map((c) => (
                        <tr
                          key={c.column_id}
                          className="border-t border-neutral-100 dark:border-neutral-800"
                        >
                          <td className="py-1.5 pr-4">{c.column_name}</td>
                          <td className="py-1.5 pr-4 text-right tabular-nums">
                            {formatUsd(c.cost_usd)}
                          </td>
                          <td className="py-1.5 pr-4 text-right tabular-nums">
                            {c.cells}
                          </td>
                          <td className="py-1.5 pr-4 text-right tabular-nums">
                            {c.generations}
                          </td>
                          <td className="py-1.5 text-right tabular-nums">
                            {(
                              c.prompt_tokens + c.completion_tokens
                            ).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
                  {t("tableCost.noSpend")}
                </p>
              )}

              <button
                type="button"
                onClick={() => void load()}
                className="mt-3 rounded-md border border-neutral-300 px-2.5 py-1 text-xs text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
              >
                {t("common.refresh")}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
