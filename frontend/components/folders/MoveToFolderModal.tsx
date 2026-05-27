"use client";

import { useMemo, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT, type TranslationKey } from "@/lib/i18n-context";

/**
 * Shared "Move N items to a folder…" modal — used by the bulk-move
 * action on /publish/domains, /library, and /prompts.
 *
 * The picker is a flat scrollable list with indentation derived from
 * tree depth, so deeply-nested folder structures still read clearly.
 * For flat folder models (library tables) the depth lookup just always
 * resolves to 0, no special-casing needed.
 *
 * "Root" appears as a virtual first row — picks it to move the selected
 * items out of any folder (folder_id = null on the wire).
 *
 * The component is intentionally surface-agnostic: callers pass in the
 * folder list and the i18n keys for the title / subtitle / no-folders
 * fallback. This used to live in `components/domains/` with a hardcoded
 * `DomainFolder` type, copy-pasting for /library and /prompts would
 * have been the easy mistake here.
 */
export interface FolderLike {
  id: number;
  name: string;
  /** Self-referencing FK. Flat folder models (library tables) leave
   *  this undefined or null — the modal renders them at depth 0. */
  parent_id?: number | null;
}

export function MoveToFolderModal<F extends FolderLike>({
  folders,
  selectedCount,
  onClose,
  onConfirm,
  busy,
  titleKey = "moveToFolder.title",
  subtitleKey = "moveToFolder.subtitle",
  rootKey = "moveToFolder.root",
  noFoldersKey = "moveToFolder.noFolders",
  confirmKey = "moveToFolder.confirm",
}: {
  folders: F[];
  /** How many items are about to be moved — shown in the title via {count}. */
  selectedCount: number;
  onClose: () => void;
  /** ``null`` = move to implicit root (no folder). */
  onConfirm: (folderId: number | null) => void;
  busy?: boolean;
  /** Override i18n keys when the caller wants surface-specific copy
   *  (e.g. "Move {count} prompts" vs the default "Move {count} items"). */
  titleKey?: TranslationKey;
  subtitleKey?: TranslationKey;
  rootKey?: TranslationKey;
  noFoldersKey?: TranslationKey;
  confirmKey?: TranslationKey;
}) {
  const { t } = useT();
  const [picked, setPicked] = useState<number | null | undefined>(undefined);

  // Build a depth lookup so we can indent nested entries. Single-pass
  // memoized walk. For flat folder models (no parent_id) every entry
  // resolves to 0.
  const depthOf = useMemo(() => {
    const byId = new Map(folders.map((f) => [f.id, f] as const));
    const cache = new Map<number, number>();
    function walk(id: number): number {
      if (cache.has(id)) return cache.get(id)!;
      const f = byId.get(id);
      const parent = f?.parent_id ?? null;
      if (!f || parent == null) {
        cache.set(id, 0);
        return 0;
      }
      const d = walk(parent) + 1;
      cache.set(id, d);
      return d;
    }
    for (const f of folders) walk(f.id);
    return cache;
  }, [folders]);

  // Render in tree pre-order so the flat list reads top-down. Sort
  // siblings by name for stability across renders.
  const ordered = useMemo(() => {
    const byParent = new Map<number | null, F[]>();
    for (const f of folders) {
      const k = f.parent_id ?? null;
      const arr = byParent.get(k) ?? [];
      arr.push(f);
      byParent.set(k, arr);
    }
    for (const arr of byParent.values()) arr.sort((a, b) => a.name.localeCompare(b.name));
    const out: F[] = [];
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
          {t(titleKey, { count: selectedCount })}
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t(subtitleKey)}
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
            {t(rootKey)}
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
              {t(noFoldersKey)}
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
            {busy ? t("common.loading") : t(confirmKey)}
          </button>
        </div>
      </div>
    </Modal>
  );
}
