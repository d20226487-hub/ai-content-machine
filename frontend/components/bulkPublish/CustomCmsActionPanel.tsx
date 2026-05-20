"use client";

import { useT } from "@/lib/i18n-context";
import type { PublishOperation } from "@/lib/publishBulk";

/**
 * Custom-CMS-side of the operation knob.
 *
 * Replaces the placeholder this component used to be — it now exposes the
 * full create / update / upsert triple. The server-side wiring lives in
 * ``app/services/bulk_publish.py``: when ``domain.cms_type == "custom"``
 * the run.operation value is injected into the outgoing body as the
 * ``action`` field, and the WP-only find_post path is skipped.
 *
 * Per-action requirements (enforced at submit time by the parent):
 *   - Create  → slug + title + content mandatory
 *   - Update  → id mandatory  (content / title etc. carry the new values)
 *   - Upsert  → slug + title + content mandatory  (CRM upsert falls back
 *               to create when the slug doesn't exist; on the existing-
 *               page path, the CRM treats this like an update by slug)
 *
 * State is owned by the parent (matches the WordPress panel pattern) so
 * the saved-mapping load / soft-preserve logic in BulkPublishModal can
 * apply uniformly.
 */
export function CustomCmsActionPanel({
  operation,
  onOperationChange,
}: {
  operation: PublishOperation;
  onOperationChange: (op: PublishOperation) => void;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.operation")}
      </span>
      <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
        {(["create", "update", "upsert"] as const).map((op) => (
          <button
            key={op}
            type="button"
            onClick={() => onOperationChange(op)}
            className={
              "rounded px-3 py-1 text-sm font-medium transition-colors " +
              (operation === op
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {op === "create"
              ? t("bulkPub.opCreate")
              : op === "update"
              ? t("bulkPub.opUpdate")
              : t("bulkPub.opUpsert")}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {operation === "create"
          ? t("bulkPub.customCreateHint")
          : operation === "update"
          ? t("bulkPub.customUpdateHint")
          : t("bulkPub.customUpsertHint")}
      </p>
    </div>
  );
}
