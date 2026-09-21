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
  options = ["wordpress", "custom", "films"],
}: {
  value: CmsType;
  onChange: (v: CmsType) => void;
  /** Which CMS types to offer. Single-item publish passes WordPress + Custom
   *  only — Films sites take table rows, not a single article. */
  options?: readonly CmsType[];
}) {
  const { t } = useT();
  const label: Record<CmsType, string> = {
    wordpress: t("bulkPub.cmsTypeWordPress"),
    custom: t("bulkPub.cmsTypeCustom"),
    films: t("bulkPub.cmsTypeFilms"),
  };
  const hint: Record<CmsType, string> = {
    wordpress: t("bulkPub.cmsTypeWordPressHint"),
    custom: t("bulkPub.cmsTypeCustomHint"),
    films: t("bulkPub.cmsTypeFilmsHint"),
  };
  return (
    <div>
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("bulkPub.cmsType")}
      </span>
      <div className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700">
        {options.map((c) => (
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
            {label[c]}
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {hint[value]}
      </p>
    </div>
  );
}
