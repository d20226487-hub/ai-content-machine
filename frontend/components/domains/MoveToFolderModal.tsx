"use client";

import { useMemo, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import type { DomainFolder } from "@/lib/domains";

/**
 * Folder picker for the "Move to folder…" bulk action.
 *
 * The picker is a flat scrollable list with indentation derived from
 * tree depth. We could also render the full Drive-style tree here, but
 * for v1 the flat-with-indent view is simpler and uses the same
 * mental model as the breadcrumb / sidebar (which already shows the
 * hierarchy).
 *
 * "Root" appears as a virtual first row — picks it to move the
 * selected domains out of any folder (folder_id = null on the wire).
 */
export function MoveToFolderModal({
  folders,
  selectedCount,
  onClose,
  onConfirm,
  busy,
}: {
  folders: DomainFolder[];
  /** How many domains are about to be moved — shown in the title. */
  selectedCount: number;
  onClose: () => void;
  /** ``null`` = move to implicit root. */
  onConfirm: (folderId: number | null) => void;
  busy?: boolean;
}) {
  const { t } = useT();
  const [picked, setPicked] = useState<number | null | undefined>(undefined);

  // Build a depth lookup so we can indent. Same single-pass algorithm
  // as the sidebar's children-map plus a memoized walk per node.
  const depthOf = useMemo(() => {
    const byId = new Map(folders.map((f) => [f.id, f] as const));
    const cache = new Map<number, number>();
    function walk(id: number): number {
      if (cache.has(id)) return cache.get(id)!;
      const f = byId.get(id);
      if (!f || f.parent_id == null) {
        cache.set(id, 0);
        return 0;
      }
      const d = walk(f.parent_id) + 1;
      cache.set(id, d);
      return d;
    }
    for (const f of folders) walk(f.id);
    return cache;
  }, [folders]);

  // Render in tree pre-order so the flat list reads top-down. Sort
  // siblings by name for stability.
  const ordered = useMemo(() => {
    const byParent = new Map<number | null, DomainFolder[]>();
    for (const f of folders) {
      const k = f.parent_id;
      const arr = byParent.get(k) ?? [];
      arr.push(f);
      byParent.set(k, arr);
    }
    for (const arr of byParent.values()) arr.sort((a, b) => a.name.localeCompare(b.name));
    const out: DomainFolder[] = [];
    function visit(parent: number | null) {
      for (const f of byParent.get(parent) ?? []) {
        out.push(f);
        visit(f.id);
      }
    }
    visit(null);
    return out;
  }, [folders]);

  return (
    <Modal onClose={onClose} size="max-w-md">
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("moveToFolder.title", { count: selectedCount })}
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("moveToFolder.subtitle")}
        </p>

        <div className="max-h-72 overflow-auto rounded-md border border-neutral-200 dark:border-neutral-800">
          <button
            type="button"
            onClick={() => setPicked(null)}
            className={
              "block w-full px-3 py-1.5 text-left text-sm " +
              (picked === null
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "hover:bg-neutral-50 dark:hover:bg-neutral-800")
            }
          >
            {t("moveToFolder.root")}
          </button>
          {ordered.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setPicked(f.id)}
              className={
                "block w-full px-3 py-1.5 text-left text-sm " +
                (picked === f.id
                  ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "hover:bg-neutral-50 dark:hover:bg-neutral-800")
              }
              style={{ paddingLeft: 12 + (depthOf.get(f.id) ?? 0) * 16 }}
            >
              {f.name}
            </button>
          ))}
          {ordered.length === 0 && (
            <p className="px-3 py-2 text-xs text-neutral-500 dark:text-neutral-400">
              {t("moveToFolder.noFolders")}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            disabled={picked === undefined || busy}
            onClick={() => picked !== undefined && onConfirm(picked)}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("common.loading") : t("moveToFolder.confirm")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
