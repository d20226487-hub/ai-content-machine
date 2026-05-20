"use client";

import { useT } from "@/lib/i18n-context";
import type {
  OnSlugConflict,
  PublishLookupKind,
  PublishOperation,
} from "@/lib/publishBulk";
import type { BulkColumn } from "@/lib/types";

/**
 * WP-specific knobs that live above the domain picker in BulkPublishModal.
 *
 * Three logical sections, gated by which operation is active:
 *   - Operation toggle (Create vs Update) — always shown
 *   - On-slug-conflict panel — shown when operation === "create"
 *   - Lookup controls (id/slug + column) — shown when operation === "update"
 *
 * Custom CMS has its own action model (create / update / upsert) and uses
 * `CustomCmsActionPanel` instead. The parent renders one panel or the other
 * based on the segmented control at the top.
 *
 * State is fully owned by the parent — this component is stateless and
 * receives every value + setter as a prop. Keeps the soft-preserve logic
 * (the "user touched the operation knob" ref) intact in the parent.
 */
export function WordPressOperationPanel({
  operation,
  onOperationChange,
  onSlugConflict,
  onSlugConflictChange,
  lookupKind,
  onLookupKindChange,
  lookupColumnId,
  onLookupColumnIdChange,
  columns,
  fieldToColumn,
}: {
  operation: PublishOperation;
  onOperationChange: (op: PublishOperation) => void;
  onSlugConflict: OnSlugConflict;
  onSlugConflictChange: (oc: OnSlugConflict) => void;
  lookupKind: PublishLookupKind;
  onLookupKindChange: (k: PublishLookupKind) => void;
  lookupColumnId: number | "";
  onLookupColumnIdChange: (id: number | "") => void;
  columns: BulkColumn[];
  fieldToColumn: Record<string, number>;
}) {
  const { t } = useT();
  return (
    <>
      {/* Operation toggle: Create vs Update. */}
      <div>
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.operation")}
        </span>
        <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
          {(["create", "update"] as const).map((op) => (
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
              {op === "create" ? t("bulkPub.opCreate") : t("bulkPub.opUpdate")}
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {operation === "create"
            ? t("bulkPub.opCreateHint")
            : t("bulkPub.opUpdateHint")}
        </p>
      </div>

      {/* Create mode: what to do when a row's slug already exists. */}
      {operation === "create" && (
        <div className="rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-800/30">
          <PanelField label={t("bulkPub.onSlugConflict")}>
            <div className="inline-flex rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900">
              {(["create", "skip", "update"] as const).map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => onSlugConflictChange(opt)}
                  className={
                    "rounded px-3 py-1 text-xs font-medium transition-colors " +
                    (onSlugConflict === opt
                      ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                      : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                  }
                >
                  {opt === "create"
                    ? t("bulkPub.onSlugCreate")
                    : opt === "skip"
                    ? t("bulkPub.onSlugSkip")
                    : t("bulkPub.onSlugUpdate")}
                </button>
              ))}
            </div>
          </PanelField>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {onSlugConflict === "create"
              ? t("bulkPub.onSlugCreateHint")
              : onSlugConflict === "skip"
              ? t("bulkPub.onSlugSkipHint")
              : t("bulkPub.onSlugUpdateHint")}
          </p>
          {onSlugConflict !== "create" && !("slug" in fieldToColumn) && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
              {t("bulkPub.slugConflictNeedsSlug")}
            </p>
          )}
        </div>
      )}

      {/* Update mode: look-up controls. */}
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
            {lookupKind === "id"
              ? t("bulkPub.lookupHintId")
              : t("bulkPub.lookupHintSlug")}
          </p>
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
            {t("bulkPub.updateBlankHint")}
          </p>
        </div>
      )}
    </>
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
