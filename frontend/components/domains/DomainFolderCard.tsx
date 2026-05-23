"use client";

import { useT } from "@/lib/i18n-context";
import type { DomainFolder } from "@/lib/domains";

/**
 * One folder shown as a card in the /publish/domains grid.
 *
 * Replaces the per-row entry in the old left-sidebar tree. The card itself
 * is the primary affordance: click anywhere → open the folder. The
 * rename / delete buttons live in the top-right and reveal on hover so
 * they don't compete visually with the open action. Matches the
 * /library FolderCard pattern — folder browsing on the two pages should
 * feel the same.
 *
 * `subfolderCount` is rendered alongside the domain count when present
 * (domain folders support nesting; /library's tables are flat, so its
 * card only shows a table count). The badge text degrades gracefully
 * when either count is null/undefined.
 */
export function DomainFolderCard({
  folder,
  onOpen,
  onRename,
  onDelete,
}: {
  folder: DomainFolder;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const { t } = useT();
  const domainCount = folder.domain_count ?? 0;
  const subfolderCount = folder.subfolder_count ?? 0;

  return (
    <div className="group relative rounded-lg border border-neutral-200 bg-white p-4 shadow-sm transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-600">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-start gap-3 text-left"
      >
        <span aria-hidden="true" className="text-2xl leading-none">
          📁
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {folder.name}
          </p>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("domainFolders.cardDomainCount", { count: domainCount })}
            {subfolderCount > 0 && (
              <>
                {" · "}
                {t("domainFolders.cardSubfolderCount", { count: subfolderCount })}
              </>
            )}
          </p>
        </div>
      </button>
      {/* Action buttons reveal on hover so the card stays calm when
          you're just scanning the grid. */}
      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRename();
          }}
          className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        >
          {t("common.rename")}
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
        >
          {t("common.delete")}
        </button>
      </div>
    </div>
  );
}
