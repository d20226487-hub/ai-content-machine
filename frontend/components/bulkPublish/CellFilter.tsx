"use client";

import { useT } from "@/lib/i18n-context";
import type { CellFilter as CellFilterValue } from "@/lib/publishBulk";

/**
 * Cell-level scope for a bulk run. Three exclusive choices:
 *   - all          — every candidate row gets sent
 *   - unpublished  — only rows whose post_id_target cell is empty
 *   - failed       — only rows whose post_id_target cell holds a prior
 *                    failure marker (legacy 'failed' literal)
 *
 * Both 'unpublished' and 'failed' depend on a configured back-fill column
 * (post_id_target). We surface an amber hint when one of those modes is
 * active without that column set; the parent ultimately uses
 * candidatePreview to refuse the submit, but the inline hint helps users
 * spot the misconfig before they hit the button.
 */
export function CellFilter({
  value,
  onChange,
  hasPostIdTarget,
}: {
  value: CellFilterValue;
  onChange: (v: CellFilterValue) => void;
  hasPostIdTarget: boolean;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.cellFilter")}
      </span>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "all"}
            onChange={() => onChange("all")}
          />
          {t("bulkPub.cellAll")}
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "unpublished"}
            onChange={() => onChange("unpublished")}
          />
          {t("bulkPub.cellUnpublished")}
        </label>
        <label className="flex items-center gap-1">
          <input
            type="radio"
            checked={value === "failed"}
            onChange={() => onChange("failed")}
          />
          {t("bulkPub.cellFailed")}
        </label>
      </div>
      {value !== "all" && !hasPostIdTarget && (
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
          {t("bulkPub.cellNeedTarget")}
        </p>
      )}
    </div>
  );
}
