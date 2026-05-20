"use client";

import { useT } from "@/lib/i18n-context";
import type { RowFilter as RowFilterValue } from "@/lib/publishBulk";

/**
 * Row-selection scope for a bulk run. Three exclusive choices:
 *   - all       — every row in the table
 *   - selected  — only the row ids the caller passed in (disabled when 0)
 *   - range     — a numeric inclusive slice; shows two inputs when active
 *
 * Stateless: the parent owns the radio value and the range bounds. Range
 * inputs are stringly-typed on purpose — letting the user clear the field
 * mid-edit without bouncing back to "1" was the original UX choice. The
 * parent coerces with `Number(...) || fallback` at submit time.
 */
export function RowFilter({
  value,
  onChange,
  rangeStart,
  rangeEnd,
  onRangeStartChange,
  onRangeEndChange,
  totalRows,
  selectedCount,
}: {
  value: RowFilterValue;
  onChange: (v: RowFilterValue) => void;
  rangeStart: string;
  rangeEnd: string;
  onRangeStartChange: (v: string) => void;
  onRangeEndChange: (v: string) => void;
  totalRows: number;
  selectedCount: number;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.rows")}
      </span>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "all"}
            onChange={() => onChange("all")}
          />
          {t("bulkPub.rowsAll", { count: totalRows })}
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "selected"}
            onChange={() => onChange("selected")}
            disabled={selectedCount === 0}
          />
          {t("bulkPub.rowsSelected", { count: selectedCount })}
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "range"}
            onChange={() => onChange("range")}
          />
          {t("bulkPub.rowsRange")}
        </label>
        {value === "range" && (
          <span className="flex items-center gap-1 text-xs text-neutral-600 dark:text-neutral-400">
            <input
              type="number"
              min={1}
              value={rangeStart}
              onChange={(e) => onRangeStartChange(e.target.value)}
              className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span>–</span>
            <input
              type="number"
              min={1}
              value={rangeEnd}
              onChange={(e) => onRangeEndChange(e.target.value)}
              className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          </span>
        )}
      </div>
    </div>
  );
}
