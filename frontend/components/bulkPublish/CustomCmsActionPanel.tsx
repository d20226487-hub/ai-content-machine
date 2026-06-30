"use client";

import { useT } from "@/lib/i18n-context";
import type { PublishLookupKind, PublishOperation } from "@/lib/publishBulk";
import type { BulkColumn } from "@/lib/types";

/**
 * Custom-CMS-side of the operation knob.
 *
 * Exposes the full create / update / upsert triple. The server-side
 * wiring lives in ``app/services/bulk_publish.py``: when
 * ``domain.cms_type == "custom"`` the run.operation value is injected
 * into the outgoing body as the ``action`` field, and the WP-only
 * find_post path is skipped.
 *
 * Per-action requirements (enforced at submit time by the parent):
 *   - Create  → slug + title + content mandatory
 *   - Update  → "Find existing posts by" panel — pick the id OR slug column
 *               (the upstream resolves an update by either, with action=update)
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
  lookupKind,
  onLookupKindChange,
  lookupColumnId,
  onLookupColumnIdChange,
  columns,
  operations = ["create", "update", "upsert"],
}: {
  operation: PublishOperation;
  onOperationChange: (op: PublishOperation) => void;
  /** Update-mode only. id or slug — the upstream resolves an update by the
   *  identifier carried in the body. Same prop shape as the WP panel so the
   *  two panels share parent state. */
  lookupKind: PublishLookupKind;
  onLookupKindChange: (k: PublishLookupKind) => void;
  lookupColumnId: number | "";
  onLookupColumnIdChange: (id: number | "") => void;
  columns: BulkColumn[];
  /** Which operations to offer. The 'match' page type passes
   *  ["create","update"] (no upsert endpoint exists for it). */
  operations?: readonly PublishOperation[];
}) {
  const { t } = useT();
  return (
    <div className="space-y-3">
      <div>
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.operation")}
        </span>
        <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
          {operations.map((op) => (
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

      {/* "Find existing posts by" — Update-only. Mirrors the WP panel so
          operators get one consistent mental model: the lookup column is
          where the OLD id/slug lives, while the field-mapping panel
          below is where the NEW values get set. With those split, you
          can rename a slug as part of an update without the lookup
          chasing the new value. */}
      {operation === "update" && (
        <div className="rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-800/30">
          <div className="grid grid-cols-2 gap-3">
            <PanelField label={t("bulkPub.lookupKind")}>
              <div className="inline-flex rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900">
                {(["id", "slug"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => onLookupKindChange(k)}
                    className={
                      "rounded px-3 py-1 text-xs font-medium transition-colors " +
                      (lookupKind === k
                        ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                        : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                    }
                  >
                    {k === "id"
                      ? t("bulkPub.lookupKindId")
                      : t("bulkPub.lookupKindSlug")}
                  </button>
                ))}
              </div>
            </PanelField>
            <PanelField label={t("bulkPub.lookupColumn")}>
              <select
                value={lookupColumnId}
                onChange={(e) =>
                  onLookupColumnIdChange(
                    e.target.value === "" ? "" : Number(e.target.value),
                  )
                }
                className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">— {t("bulkPub.lookupColumnPlaceholder")} —</option>
                {columns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </PanelField>
          </div>
          <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            {t("bulkPub.customLookupHint")}
          </p>
        </div>
      )}
    </div>
  );
}

function PanelField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      {children}
    </label>
  );
}
