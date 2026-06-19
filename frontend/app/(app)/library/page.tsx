"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { GdocsImportModal } from "@/components/GdocsImportModal";
import { ImportCsvModal } from "@/components/ImportCsvModal";
import { UserChip } from "@/components/UserChip";
import { MoveToFolderModal } from "@/components/folders/MoveToFolderModal";
import { ApiError } from "@/lib/api";
import type { GdocsImportRun } from "@/lib/gdocsImport";
import { useT } from "@/lib/i18n-context";
import {
  bulkMoveTables,
  createFolder,
  createTable,
  deleteFolder,
  deleteTable,
  duplicateTable,
  getTrashCount,
  listFolders,
  listTables,
  moveFolder,
  renameFolder,
  renameTable,
  type BulkFolder,
} from "@/lib/library";
import type { BulkTable, BulkTableListItem } from "@/lib/types";

export default function LibraryPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const { t } = useT();

  const folder = sp.get("folder") ? Number(sp.get("folder")) : null;
  const q = sp.get("q") ?? "";
  const page = Number(sp.get("page") ?? "1");
  const pageSize = Number(sp.get("size") ?? "50");

  function updateParams(
    updates: Record<string, string | number | null | undefined>,
    opts: { push?: boolean } = {},
  ) {
    const next = new URLSearchParams(Array.from(sp.entries()));
    for (const [k, v] of Object.entries(updates)) {
      if (v === null || v === undefined || v === "") {
        next.delete(k);
      } else {
        next.set(k, String(v));
      }
    }
    const qs = next.toString();
    const path = `/library${qs ? "?" + qs : ""}`;
    if (opts.push) router.push(path);
    else router.replace(path);
  }

  const [folders, setFolders] = useState<BulkFolder[]>([]);
  const [items, setItems] = useState<BulkTableListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [trashCount, setTrashCount] = useState<number>(0);

  const refreshTrashCount = useCallback(async () => {
    try {
      const { count } = await getTrashCount();
      setTrashCount(count);
    } catch {
      // non-critical — the badge just won't show. Don't surface to the user.
    }
  }, []);

  useEffect(() => {
    void refreshTrashCount();
  }, [refreshTrashCount]);

  const [searchDraft, setSearchDraft] = useState(q);
  const [debouncedSearch, setDebouncedSearch] = useState(q);
  const [showImport, setShowImport] = useState(false);
  const [showGdocsImport, setShowGdocsImport] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  // Bulk-select: cross-page persistent selection (same model used by
  // /publish/domains). Only cleared by the "Clear" button or a
  // successful bulk action.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [moving, setMoving] = useState(false);

  useEffect(() => {
    setSearchDraft(q);
    setDebouncedSearch(q);
  }, [q]);

  useEffect(() => {
    const tm = setTimeout(() => setDebouncedSearch(searchDraft), 250);
    return () => clearTimeout(tm);
  }, [searchDraft]);

  useEffect(() => {
    if (debouncedSearch !== q) {
      updateParams({ q: debouncedSearch || null, page: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const refreshFolders = useCallback(async () => {
    try {
      const fs = await listFolders({ with_counts: true });
      setFolders(fs);
    } catch (err) {
      setError(err);
    }
  }, []);

  useEffect(() => {
    void refreshFolders();
  }, [refreshFolders]);

  const refreshTables = useCallback(async () => {
    setItems(null);
    try {
      // Root view filters to tables NOT in any folder (folder_id=0 is
      // the backend's "uncategorized" sentinel — see library.list_tables).
      // Previously the root sent no folder_id param and the backend
      // returned everything, which cluttered the page with tables that
      // already lived inside a folder.
      const r = await listTables({
        folder_id: folder ?? 0,
        q,
        page,
        page_size: pageSize,
      });
      setItems(r.items);
      setTotal(r.total);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [folder, q, page, pageSize]);

  useEffect(() => {
    void refreshTables();
  }, [refreshTables]);

  const folderById = useMemo(
    () => new Map(folders.map((f) => [f.id, f])),
    [folders],
  );
  const currentFolder = folder !== null ? folderById.get(folder) ?? null : null;

  // Full ancestor chain (outermost → current) for the breadcrumb, walked up
  // via parent_id. The `guard` set stops a malformed cycle from looping.
  const folderPath = useMemo<BulkFolder[]>(() => {
    const path: BulkFolder[] = [];
    let cur: BulkFolder | null = currentFolder;
    const guard = new Set<number>();
    while (cur && !guard.has(cur.id)) {
      guard.add(cur.id);
      path.unshift(cur);
      cur = cur.parent_id != null ? folderById.get(cur.parent_id) ?? null : null;
    }
    return path;
  }, [currentFolder, folderById]);

  // Folder cards = the direct children of the folder we're viewing
  // (top-level folders when at the root).
  const visibleFolders = useMemo(
    () => folders.filter((f) => (f.parent_id ?? null) === (folder ?? null)),
    [folders, folder],
  );

  // parent_id → direct children, for the folder-move target list. A folder
  // can't move into itself or any of its descendants (would cycle), so we
  // walk its subtree to exclude them from the "Move to" options.
  const childrenByParent = useMemo(() => {
    const m = new Map<number | null, BulkFolder[]>();
    for (const f of folders) {
      const key = f.parent_id ?? null;
      const arr = m.get(key);
      if (arr) arr.push(f);
      else m.set(key, [f]);
    }
    return m;
  }, [folders]);

  const descendantIdsOf = useCallback(
    (rootId: number): Set<number> => {
      const out = new Set<number>();
      const stack = [rootId];
      while (stack.length) {
        const id = stack.pop()!;
        for (const c of childrenByParent.get(id) ?? []) {
          if (!out.has(c.id)) {
            out.add(c.id);
            stack.push(c.id);
          }
        }
      }
      return out;
    },
    [childrenByParent],
  );

  function navigateFolder(id: number | null) {
    updateParams({ folder: id, page: null }, { push: true });
  }

  async function onCreateFolder() {
    const name = window.prompt(t("library.folderNamePrompt"));
    if (!name?.trim()) return;
    try {
      // Nest the new folder under whatever folder we're currently viewing
      // (null at root → top-level). This is the fix for "subfolders landed
      // in root": the parent was never sent.
      await createFolder(name.trim(), folder);
      await refreshFolders();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.createFailed"));
    }
  }

  async function onRenameFolder(f: BulkFolder) {
    const name = window.prompt(t("library.renameFolderPrompt"), f.name);
    if (!name?.trim() || name.trim() === f.name) return;
    try {
      await renameFolder(f.id, name.trim());
      await refreshFolders();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.renameFailed"));
    }
  }

  async function onDeleteFolder(f: BulkFolder) {
    if (!window.confirm(t("library.confirmDeleteFolder", { name: f.name }))) return;
    try {
      await deleteFolder(f.id);
      await refreshFolders();
      if (folder === f.id) navigateFolder(null);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  async function onMoveFolder(f: BulkFolder, newParentId: number | null) {
    if ((f.parent_id ?? null) === newParentId) return; // no-op
    try {
      await moveFolder(f.id, newParentId);
      await refreshFolders();
    } catch (err) {
      // 400 = would create a cycle (server guard); surface its message.
      alert(err instanceof ApiError ? err.message : t("common.moveFailed"));
    }
  }

  async function onCreateTable() {
    const name = window.prompt(t("library.newTablePrompt"));
    if (!name?.trim()) return;
    try {
      const table = await createTable({
        name: name.trim(),
        folder_id: folder,
      });
      router.push(`/library/${table.id}`);
    } catch (e) {
      setError(e);
    }
  }

  async function onDuplicate(id: number) {
    try {
      const dup = await duplicateTable(id);
      await refreshTables();
      await refreshFolders();
      router.push(`/library/${dup.id}`);
    } catch (e) {
      setError(e);
    }
  }

  async function onDelete(tab: BulkTableListItem) {
    if (!window.confirm(t("library.confirmDeleteTable", { name: tab.name }))) return;
    try {
      await deleteTable(tab.id);
      await refreshTables();
      await refreshFolders();
      await refreshTrashCount();
    } catch (e) {
      // 409 = in-flight publish run is using this table. Surface clean message.
      if (e instanceof ApiError && e.status === 409) {
        alert(e.message || t("library.deleteBlockedInflight"));
      } else {
        setError(e);
      }
    }
  }

  // ----- bulk selection -----

  function toggleSelect(id: number) {
    setSelectedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allOnPageSelected =
    items != null && items.length > 0 && items.every((it) => selectedIds.has(it.id));

  function toggleSelectAllOnPage() {
    if (!items) return;
    setSelectedIds((s) => {
      const next = new Set(s);
      if (allOnPageSelected) {
        for (const it of items) next.delete(it.id);
      } else {
        for (const it of items) next.add(it.id);
      }
      return next;
    });
  }

  async function onConfirmBulkMove(folderId: number | null) {
    if (selectedIds.size === 0 || moving) return;
    setMoving(true);
    try {
      await bulkMoveTables({
        table_ids: Array.from(selectedIds),
        folder_id: folderId,
      });
      setSelectedIds(new Set());
      setShowMoveModal(false);
      await refreshTables();
      await refreshFolders();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setMoving(false);
    }
  }

  async function onConfirmRename(id: number) {
    const name = renameValue.trim();
    if (!name) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await renameTable(id, { name });
      setItems((cur) =>
        cur ? cur.map((x) => (x.id === id ? { ...x, name: updated.name } : x)) : cur,
      );
      setRenamingId(null);
    } catch (e) {
      setError(e);
    }
  }

  async function onMoveToFolder(tab: BulkTableListItem, targetFolderId: number | null) {
    try {
      await renameTable(tab.id, { folder_id: targetFolderId });
      await refreshTables();
      await refreshFolders();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.moveFailed"));
    }
  }

  function onImported(tables: BulkTable[], opts: { navigate: boolean }) {
    // Single clean import → open the new table (unchanged behavior). Multiple
    // → stay on the list and refresh so all the new tables show up.
    if (opts.navigate && tables[0]) {
      router.push(`/library/${tables[0].id}`);
      return;
    }
    void refreshTables();
    void refreshFolders();
  }

  function onGdocsQueued(run: GdocsImportRun) {
    setShowGdocsImport(false);
    router.push(`/library/import/gdocs/${run.id}`);
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <main className="mx-auto max-w-6xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Breadcrumb
            path={folderPath}
            onJump={(id) => navigateFolder(id)}
            rootLabel={t("library.breadcrumbRoot")}
          />
          <h1 className="mt-1 truncate text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {currentFolder?.name ?? t("library.title")}
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {currentFolder ? t("library.subtitleFolder") : t("library.subtitleRoot")}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {trashCount > 0 && (
            <Link
              href="/library/trash"
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              {t("library.trashLinkWithCount", { count: trashCount })}
            </Link>
          )}
          <button
            onClick={onCreateFolder}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("library.newFolder")}
          </button>
          <button
            onClick={() => setShowImport(true)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("library.importCsv")}
          </button>
          <button
            onClick={() => setShowGdocsImport(true)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("library.importGdocs")}
          </button>
          <button
            onClick={onCreateTable}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("library.newTable")}
          </button>
        </div>
      </div>

      <div className="mt-5">
        <input
          type="text"
          placeholder={
            currentFolder
              ? t("library.searchInFolderPlaceholder", { folder: currentFolder.name })
              : t("library.searchPlaceholder")
          }
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          className="block w-full max-w-sm rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </div>

      {error != null && (
        <div className="mt-6">
          <ErrorPanel title={t("common.failedToLoad")} error={error} />
        </div>
      )}

      {visibleFolders.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {currentFolder
              ? t("library.subfoldersHeading", { count: visibleFolders.length })
              : t("library.foldersHeading", { count: visibleFolders.length })}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            {visibleFolders.map((f) => {
              const blocked = descendantIdsOf(f.id);
              const moveTargets = folders.filter(
                (t2) => t2.id !== f.id && !blocked.has(t2.id),
              );
              return (
                <FolderCard
                  key={f.id}
                  folder={f}
                  onOpen={() => navigateFolder(f.id)}
                  onRename={() => onRenameFolder(f)}
                  onDelete={() => onDeleteFolder(f)}
                  onMove={(parentId) => void onMoveFolder(f, parentId)}
                  moveTargets={moveTargets}
                  renameLabel={t("common.rename")}
                  deleteLabel={t("common.delete")}
                  moveLabel={t("common.move")}
                  moveRootLabel={t("library.breadcrumbRoot")}
                  tableCountLabel={t("library.folderTablesCount", { count: f.table_count ?? 0 })}
                  subfolderCountLabel={
                    (f.subfolder_count ?? 0) > 0
                      ? t("library.folderSubfoldersCount", { count: f.subfolder_count ?? 0 })
                      : null
                  }
                />
              );
            })}
          </div>
        </section>
      )}

      {/* Bulk-action bar — appears only when ≥ 1 card is checked.
          Selection persists across pages: the count here is the full
          selection, not just "on this page". */}
      {selectedIds.size > 0 && (
        <div className="mt-4 flex items-center justify-between rounded-md border border-neutral-300 bg-neutral-50 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900">
          <span className="text-neutral-700 dark:text-neutral-300">
            {t("library.selectedCount", { count: selectedIds.size })}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="text-xs text-neutral-500 hover:underline dark:text-neutral-400"
            >
              {t("common.clearSelection")}
            </button>
            <button
              type="button"
              onClick={() => setShowMoveModal(true)}
              className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              {t("library.moveToFolder")}
            </button>
          </div>
        </div>
      )}

      <section className="mt-6">
        <h2 className="mb-2 flex items-center justify-between text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          <span>
            {t("library.tablesHeading")} {total > 0 && `(${total})`}
          </span>
          {items && items.length > 0 && (
            <label className="inline-flex items-center gap-1.5 normal-case tracking-normal text-[11px] text-neutral-500 dark:text-neutral-400">
              <input
                type="checkbox"
                checked={allOnPageSelected}
                onChange={toggleSelectAllOnPage}
                className="h-3.5 w-3.5"
              />
              {t("library.selectAllOnPage")}
            </label>
          )}
        </h2>

        {!items && !error && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{t("common.loading")}</p>
        )}

        {items && items.length === 0 && (
          <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
            {q
              ? t("library.empty.search")
              : currentFolder
                ? t("library.empty.folder")
                : t("library.empty.none")}
            {!q && (
              <>
                <button
                  onClick={onCreateTable}
                  className="ml-2 font-medium text-neutral-900 underline dark:text-neutral-100"
                >
                  {t("library.empty.createOne")}
                </button>
                {t("library.empty.or")}
                <button
                  onClick={() => setShowImport(true)}
                  className="font-medium text-neutral-900 underline dark:text-neutral-100"
                >
                  {t("library.empty.importCsv")}
                </button>
                .
              </>
            )}
          </div>
        )}

        {items && items.length > 0 && (
          <ul className="grid gap-4 sm:grid-cols-2">
            {items.map((tab) => {
              const isChecked = selectedIds.has(tab.id);
              return (
              <li
                key={tab.id}
                className={
                  "rounded-lg border bg-white p-4 shadow-sm transition dark:bg-neutral-900 " +
                  (isChecked
                    ? "border-neutral-500 dark:border-neutral-500"
                    : "border-neutral-200 hover:border-neutral-300 dark:border-neutral-800 dark:hover:border-neutral-700")
                }
              >
                <div className="flex items-start justify-between gap-3">
                  {/* Selection checkbox — placed before the title so the
                      visual order matches the keyboard tab order, and
                      so the checkbox is the first hit-target. */}
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleSelect(tab.id)}
                    aria-label={t("library.selectTable", { name: tab.name })}
                    className="mt-0.5 h-4 w-4 shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    {renamingId === tab.id ? (
                      <input
                        type="text"
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void onConfirmRename(tab.id);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        onBlur={() => void onConfirmRename(tab.id)}
                        className="block w-full rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                      />
                    ) : (
                      <Link
                        href={`/library/${tab.id}`}
                        title={tab.name}
                        className="block truncate text-base font-semibold text-neutral-900 hover:underline dark:text-neutral-100"
                      >
                        {tab.name}
                      </Link>
                    )}
                    <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                      {t("library.tableMeta", {
                        cols: tab.column_count,
                        rows: tab.row_count,
                        time: new Date(tab.updated_at).toLocaleString(),
                      })}
                    </p>
                    {folder === null && tab.folder_id && folderById.has(tab.folder_id) && (
                      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                        {t("library.inFolder")}{" "}
                        <button
                          type="button"
                          onClick={() => navigateFolder(tab.folder_id!)}
                          className="text-neutral-700 underline-offset-2 hover:underline dark:text-neutral-300"
                        >
                          {folderById.get(tab.folder_id!)!.name}
                        </button>
                      </p>
                    )}
                  </div>
                  {tab.created_by_name && (
                    <div className="shrink-0">
                      <UserChip name={tab.created_by_name} />
                    </div>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                  <Link
                    href={`/library/${tab.id}`}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("common.open")}
                  </Link>
                  <button
                    onClick={() => {
                      setRenamingId(tab.id);
                      setRenameValue(tab.name);
                    }}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("common.rename")}
                  </button>
                  <button
                    onClick={() => void onDuplicate(tab.id)}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("common.duplicate")}
                  </button>
                  <MoveControl
                    table={tab}
                    folders={folders}
                    moveLabel={t("common.move")}
                    noFolderLabel={t("library.movePickerNoFolder")}
                    onMove={(fid) => void onMoveToFolder(tab, fid)}
                  />
                  <button
                    onClick={() => void onDelete(tab)}
                    className="font-medium text-red-600 hover:underline dark:text-red-400"
                  >
                    {t("common.delete")}
                  </button>
                </div>
              </li>
              );
            })}
          </ul>
        )}

        {items && total > pageSize && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-600 dark:text-neutral-400">
            <span>
              {t("common.showingRange", {
                from: (page - 1) * pageSize + 1,
                to: Math.min(page * pageSize, total),
                total,
              })}
            </span>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1">
                <span>{t("common.perPage")}</span>
                <select
                  value={pageSize}
                  onChange={(e) =>
                    updateParams({ size: Number(e.target.value), page: null })
                  }
                  className="rounded-md border border-neutral-300 bg-white px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
                >
                  {[25, 50, 100, 200].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() => updateParams({ page: Math.max(1, page - 1) })}
                disabled={page === 1}
                className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("common.prev")}
              </button>
              <span>{t("common.pageXslashY", { page, total: totalPages })}</span>
              <button
                type="button"
                onClick={() => updateParams({ page: page + 1 })}
                disabled={page * pageSize >= total}
                className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("common.nextArrow")}
              </button>
            </div>
          </div>
        )}
      </section>

      {showImport && (
        <ImportCsvModal
          onClose={() => setShowImport(false)}
          onImported={onImported}
          defaultFolderId={folder}
        />
      )}

      {showGdocsImport && (
        <GdocsImportModal
          folders={folders}
          defaultFolderId={folder}
          onClose={() => setShowGdocsImport(false)}
          onQueued={onGdocsQueued}
        />
      )}

      {showMoveModal && (
        <MoveToFolderModal
          folders={folders}
          selectedCount={selectedIds.size}
          onClose={() => setShowMoveModal(false)}
          onConfirm={(fid) => void onConfirmBulkMove(fid)}
          busy={moving}
          titleKey="library.moveModalTitle"
          subtitleKey="library.moveModalSubtitle"
        />
      )}
    </main>
  );
}

// helpers

function Breadcrumb({
  path,
  onJump,
  rootLabel,
}: {
  /** Ancestor chain, outermost first, ending at the current folder. */
  path: BulkFolder[];
  onJump: (id: number | null) => void;
  rootLabel: string;
}) {
  return (
    <nav className="flex flex-wrap items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
      <button
        type="button"
        onClick={() => onJump(null)}
        className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
      >
        {rootLabel}
      </button>
      {path.map((f, i) => {
        const isLast = i === path.length - 1;
        return (
          <span key={f.id} className="flex items-center gap-1">
            <span>/</span>
            {isLast ? (
              <span className="text-neutral-700 dark:text-neutral-300">{f.name}</span>
            ) : (
              <button
                type="button"
                onClick={() => onJump(f.id)}
                className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
              >
                {f.name}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}

function FolderCard({
  folder,
  onOpen,
  onRename,
  onDelete,
  onMove,
  moveTargets,
  renameLabel,
  deleteLabel,
  moveLabel,
  moveRootLabel,
  tableCountLabel,
  subfolderCountLabel,
}: {
  folder: BulkFolder;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
  onMove: (parentId: number | null) => void;
  /** Folders this one may move into — already excludes itself + its subtree. */
  moveTargets: BulkFolder[];
  renameLabel: string;
  deleteLabel: string;
  moveLabel: string;
  moveRootLabel: string;
  tableCountLabel: string;
  subfolderCountLabel?: string | null;
}) {
  // When the move picker is open we force the action cluster visible — a
  // native <select> can briefly steal hover off the card, which would
  // otherwise fade the (opacity-0) cluster mid-interaction.
  const [moveOpen, setMoveOpen] = useState(false);
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
            {tableCountLabel}
            {subfolderCountLabel ? ` · ${subfolderCountLabel}` : ""}
          </p>
        </div>
      </button>
      <div
        className={
          "absolute right-2 top-2 flex items-center gap-1 transition-opacity " +
          (moveOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100")
        }
      >
        {moveOpen ? (
          <select
            autoFocus
            defaultValue={folder.parent_id ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              onMove(v === "" ? null : Number(v));
              setMoveOpen(false);
            }}
            onBlur={() => setMoveOpen(false)}
            className="max-w-[160px] rounded-md border border-neutral-300 bg-white px-1.5 py-0.5 text-[11px] dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
          >
            <option value="">{moveRootLabel}</option>
            {moveTargets.map((tt) => (
              <option key={tt.id} value={tt.id}>
                {tt.name}
              </option>
            ))}
          </select>
        ) : (
          <>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setMoveOpen(true);
              }}
              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            >
              {moveLabel}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRename();
              }}
              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            >
              {renameLabel}
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
            >
              {deleteLabel}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function MoveControl({
  table,
  folders,
  moveLabel,
  noFolderLabel,
  onMove,
}: {
  table: BulkTableListItem;
  folders: BulkFolder[];
  moveLabel: string;
  noFolderLabel: string;
  onMove: (folderId: number | null) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
      >
        {moveLabel}
      </button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <select
        autoFocus
        defaultValue={table.folder_id ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          onMove(v === "" ? null : Number(v));
          setOpen(false);
        }}
        onBlur={() => setOpen(false)}
        className="rounded-md border border-neutral-300 bg-white px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
      >
        <option value="">{noFolderLabel}</option>
        {folders.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
      </select>
    </span>
  );
}
