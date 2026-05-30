"use client";

import { useT } from "@/lib/i18n-context";

/**
 * Minimal "Showing X–Y of Z · Prev/Next" footer. Server-paginated callers
 * own `page` / `pageSize` / `total` and refetch on `onPage`.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const { t } = useT();
  if (total <= 0) return null;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="mt-3 flex items-center justify-between text-xs text-neutral-600 dark:text-neutral-400">
      <span>{t("pager.showing", { from, to, total })}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="rounded-md border border-neutral-300 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
        >
          {t("pager.prev")}
        </button>
        <span className="px-2 tabular-nums">
          {t("pager.pageOf", { page, total: totalPages })}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
          className="rounded-md border border-neutral-300 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:hover:bg-neutral-800"
        >
          {t("pager.next")}
        </button>
      </div>
    </div>
  );
}
