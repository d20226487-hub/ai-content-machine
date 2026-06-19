"use client";

import { useT } from "@/lib/i18n-context";
import {
  MATCH_PAGE_ENDPOINT,
  MATCH_UPDATE_ENDPOINT,
  type CustomPageType,
} from "@/lib/publishBulk";

/**
 * Custom-CMS page-type selector (bulk publish).
 *
 * 'ordinary' (обычная) keeps today's behavior — the run uses each target
 * domain's own endpoint + body_template. 'match' (матч) pins the hardcoded
 * {@link MATCH_PAGE_ENDPOINT} endpoint + the sport field set, overriding the
 * domain config. Match is create-only, so picking it hides the operation
 * panel in the parent.
 *
 * Stateless: the parent owns the value (so the saved-mapping prefill +
 * cms-type reset logic stay in BulkPublishModal).
 */
export function CustomPageTypeSelector({
  value,
  onChange,
}: {
  value: CustomPageType;
  onChange: (next: CustomPageType) => void;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.pageType")}
      </span>
      <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
        {(["ordinary", "match"] as const).map((pt) => (
          <button
            key={pt}
            type="button"
            onClick={() => onChange(pt)}
            className={
              "rounded px-3 py-1 text-sm font-medium transition-colors " +
              (value === pt
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {pt === "ordinary"
              ? t("bulkPub.pageTypeOrdinary")
              : t("bulkPub.pageTypeMatch")}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {value === "match"
          ? t("bulkPub.pageTypeMatchHint", {
              createEndpoint: MATCH_PAGE_ENDPOINT,
              updateEndpoint: MATCH_UPDATE_ENDPOINT,
            })
          : t("bulkPub.pageTypeOrdinaryHint")}
      </p>
    </div>
  );
}
