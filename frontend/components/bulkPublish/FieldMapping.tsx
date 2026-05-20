"use client";

import type { ReactNode } from "react";

import { useT } from "@/lib/i18n-context";
import type { BulkColumn } from "@/lib/types";

export interface FieldSlot {
  key: string;
  label: string;
  required: boolean;
}

/**
 * Field-to-column mapping panel.
 *
 * The list of slots is derived by the parent — for WP runs from the active
 * profile's fields[], for Custom runs from the body_template placeholders.
 * This component just renders them and the column selects.
 *
 * The "Clear saved mapping" link is part of this panel because (a) the
 * mapping IS the data being cleared, and (b) the panel header is the
 * natural place users look when they want to reset.
 *
 * Stateless: the parent owns `fieldToColumn` and the `onClear` action so
 * the soft-preserve logic + the saved-mapping memo load can stay there.
 *
 * `emptyMessage` lets the parent override the generic "no fields detected"
 * copy with something domain-specific. Worth doing — the original generic
 * message left users guessing why fields were missing (it took a real
 * support conversation to discover the issue was "auto-pick landed on a
 * Custom CMS domain whose body_template was {x: y}, i.e. no placeholders").
 */
export function FieldMapping({
  slots,
  fieldToColumn,
  onSlotChange,
  columns,
  onClear,
  emptyMessage,
}: {
  slots: FieldSlot[];
  fieldToColumn: Record<string, number>;
  onSlotChange: (key: string, colId: number | null) => void;
  columns: BulkColumn[];
  onClear: () => void;
  emptyMessage?: ReactNode;
}) {
  const { t } = useT();
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {t("bulkPub.mapHeading")}
        </h3>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-neutral-500 underline hover:text-red-600 dark:text-neutral-400 dark:hover:text-red-400"
        >
          {t("bulkPub.clearMapping")}
        </button>
      </div>
      <div className="space-y-1 text-sm">
        {slots.map((s) => (
          <div
            key={s.key}
            className="grid grid-cols-[1fr_2fr] items-center gap-2"
          >
            <span className="truncate text-neutral-700 dark:text-neutral-300">
              {s.label}
              {s.required && <span className="ml-0.5 text-red-600">*</span>}
            </span>
            <select
              value={fieldToColumn[s.key] ?? ""}
              onChange={(e) =>
                onSlotChange(s.key, e.target.value ? Number(e.target.value) : null)
              }
              className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              <option value="">{t("bulkPub.skip")}</option>
              {columns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ))}
        {slots.length === 0 && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {emptyMessage ?? t("bulkPub.noFieldsDetected")}
          </p>
        )}
      </div>
    </div>
  );
}
