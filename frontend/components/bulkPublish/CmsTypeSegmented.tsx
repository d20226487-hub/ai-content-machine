"use client";

import { useT } from "@/lib/i18n-context";
import type { CmsType } from "@/lib/domains";

/**
 * Top-of-modal segmented control that picks which CMS type the user is
 * targeting for this bulk run.
 *
 * Drives two things:
 *   - which form panels render below (WP-specific vs Custom-specific);
 *   - which domains the picker offers (filtered to the chosen type).
 *
 * This is the only NEW UX added by the refactor — everything else is a
 * structural move. Behavior-no-op aside from this control.
 */
export function CmsTypeSegmented({
  value,
  onChange,
}: {
  value: CmsType;
  onChange: (v: CmsType) => void;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.cmsType")}
      </span>
      <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
        {(["wordpress", "custom"] as const).map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            className={
              "rounded px-3 py-1 text-sm font-medium transition-colors " +
              (value === c
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {c === "wordpress"
              ? t("bulkPub.cmsTypeWordPress")
              : t("bulkPub.cmsTypeCustom")}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {value === "wordpress"
          ? t("bulkPub.cmsTypeWordPressHint")
          : t("bulkPub.cmsTypeCustomHint")}
      </p>
    </div>
  );
}
