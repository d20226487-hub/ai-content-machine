"use client";

import { useT } from "@/lib/i18n-context";
import {
  FILMS_OPERATIONS,
  FILMS_PAGE_TYPES,
  type FilmsPageType,
  type PublishOperation,
} from "@/lib/publishBulk";

/**
 * Films-side settings for a bulk run: what to publish (film / category /
 * comment) and how.
 *
 * The operations offered follow the Films import API, not a UI choice:
 * films can be created, updated or upserted; categories can only be updated
 * (the site never creates them); comments can only be added. Picking a page
 * type that doesn't support the current operation snaps the operation to the
 * first one it does support — the parent owns both values.
 *
 * No lookup panel: the site finds existing records itself (films by Kinopoisk
 * ID then exact Title, categories by ID → slug → name, comments' film by URL
 * or title), so the identifying columns are ordinary mapping slots.
 */
export function FilmsPanel({
  pageType,
  onPageTypeChange,
  operation,
  onOperationChange,
}: {
  pageType: FilmsPageType;
  onPageTypeChange: (next: FilmsPageType) => void;
  operation: PublishOperation;
  onOperationChange: (op: PublishOperation) => void;
}) {
  const { t } = useT();
  const operations = FILMS_OPERATIONS[pageType];

  const pageLabel: Record<FilmsPageType, string> = {
    films_news: t("bulkPub.filmsNews"),
    films_category: t("bulkPub.filmsCategory"),
    films_comment: t("bulkPub.filmsComment"),
  };
  const opLabel: Record<PublishOperation, string> = {
    create: t("bulkPub.opCreate"),
    update: t("bulkPub.opUpdate"),
    upsert: t("bulkPub.opUpsert"),
  };
  const hint: Record<FilmsPageType, string> = {
    films_news:
      operation === "create"
        ? t("bulkPub.filmsNewsCreateHint")
        : operation === "update"
        ? t("bulkPub.filmsNewsUpdateHint")
        : t("bulkPub.filmsNewsUpsertHint"),
    films_category: t("bulkPub.filmsCategoryHint"),
    films_comment: t("bulkPub.filmsCommentHint"),
  };

  return (
    <div className="space-y-3">
      <div>
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.pageType")}
        </span>
        <Segmented
          options={FILMS_PAGE_TYPES}
          value={pageType}
          label={(pt) => pageLabel[pt]}
          onChange={(pt) => {
            onPageTypeChange(pt);
            if (!FILMS_OPERATIONS[pt].includes(operation)) {
              onOperationChange(FILMS_OPERATIONS[pt][0]);
            }
          }}
          testId="films-page-type"
        />
      </div>

      <div>
        <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("bulkPub.operation")}
        </span>
        <Segmented
          options={operations}
          value={operation}
          label={(op) => opLabel[op]}
          onChange={onOperationChange}
          testId="films-operation"
        />
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {hint[pageType]}
        </p>
      </div>
    </div>
  );
}

function Segmented<T extends string>({
  options,
  value,
  label,
  onChange,
  testId,
}: {
  options: readonly T[];
  value: T;
  label: (v: T) => string;
  onChange: (v: T) => void;
  testId: string;
}) {
  return (
    <div
      className="inline-flex rounded-md border border-neutral-300 p-0.5 dark:border-neutral-700"
      data-testid={testId}
    >
      {options.map((o) => (
        <button
          key={o}
          type="button"
          onClick={() => onChange(o)}
          className={
            "rounded px-3 py-1 text-sm font-medium transition-colors " +
            (value === o
              ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
              : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
          }
        >
          {label(o)}
        </button>
      ))}
    </div>
  );
}
