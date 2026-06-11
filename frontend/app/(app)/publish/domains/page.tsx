"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { DomainCsvImportModal } from "@/components/DomainCsvImportModal";
import { DomainJsonImportModal } from "@/components/DomainJsonImportModal";
import { DomainModal } from "@/components/DomainModal";
import { DomainBreadcrumb } from "@/components/domains/DomainBreadcrumb";
import { DomainFolderCard } from "@/components/domains/DomainFolderCard";
import { MoveToFolderModal } from "@/components/domains/MoveToFolderModal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  bulkMoveDomains,
  bulkTrashDomains,
  createDomainFolder,
  deleteDomain,
  deleteDomainFolder,
  getDomain,
  getDomainTrashCount,
  listDomainFolders,
  listDomainsPicker,
  listDomainsPickerIds,
  testDomain,
  updateDomainFolder,
  type Domain,
  type DomainFolder,
  type DomainPickerItem,
  type DomainPickerResponse,
  type FolderScope,
  type TestConnectionResult,
} from "@/lib/domains";

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; domain: Domain }
  | { kind: "import" }
  | { kind: "importJson" }
  | { kind: "move" };

/**
 * Parse the `?folder=...` query into a FolderScope. Accepts:
 *   - undefined / empty       → "all"
 *   - "root"                  → "root"
 *   - "<int>"                 → that folder id
 *   - anything else           → "all" (graceful: a stale link doesn't break the page)
 */
function parseScope(raw: string | null): FolderScope {
  if (!raw) return "all";
  if (raw === "root") return "root";
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : "all";
}

function scopeToParam(scope: FolderScope): string | null {
  if (scope === "all") return null;
  if (scope === "root") return "root";
  return String(scope);
}

const PAGE_SIZE_OPTIONS = [50, 100, 200] as const;
const DEFAULT_PAGE_SIZE: (typeof PAGE_SIZE_OPTIONS)[number] = 50;

export default function DomainsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const isAuthorized = user && ["admin", "manager"].includes(user.role.name);

  // Folder scope lives in the URL so deep links + back/forward Just Work.
  const scope = useMemo(
    () => parseScope(searchParams.get("folder")),
    [searchParams],
  );

  function setScope(next: FolderScope) {
    const param = scopeToParam(next);
    const qs = param ? `?folder=${encodeURIComponent(param)}` : "";
    router.push(`/publish/domains${qs}`);
  }

  // -------- list state (paginated picker) --------
  //
  // The /publish/domains list page used to hit /domains and pull the
  // full Domain[]. At a thousand-plus domains the publish_config blob
  // pushed the payload past several MB. We now read from the lite
  // picker endpoint (Phase A) with pagination + server-side search,
  // and fetch the full Domain on demand for the edit modal.
  const [pickerData, setPickerData] = useState<DomainPickerResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(
    DEFAULT_PAGE_SIZE,
  );
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [folders, setFolders] = useState<DomainFolder[]>([]);
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [editLoadingId, setEditLoadingId] = useState<number | null>(null);
  const [testing, setTesting] = useState<Set<number>>(new Set());
  const [testResults, setTestResults] = useState<Record<number, TestConnectionResult>>({});
  const [trashCount, setTrashCount] = useState(0);

  // Persist-across-pages selection (user picked this in the
  // AskUserQuestion that drove this work). Selection survives page
  // changes, folder switches, and search-query edits — only the
  // "Clear selection" button or a successful bulk-move / bulk-trash
  // resets it.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [moving, setMoving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selectingAll, setSelectingAll] = useState(false);

  // ---- debounce search ----
  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query), 200);
    return () => window.clearTimeout(handle);
  }, [query]);

  // Reset to page 1 whenever the result set changes shape. Without
  // this, a user typing into the search box while on page 5 would
  // immediately see "no results" because the new (smaller) result set
  // doesn't have a page 5.
  useEffect(() => {
    setPage(1);
  }, [scope, debouncedQuery, pageSize]);

  const refreshTrashCount = useCallback(async () => {
    try {
      const { count } = await getDomainTrashCount();
      setTrashCount(count);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    if (isAuthorized) void refreshTrashCount();
  }, [isAuthorized, refreshTrashCount]);

  useEffect(() => {
    if (!authLoading && user && !isAuthorized) router.replace("/dashboard");
  }, [user, authLoading, isAuthorized, router]);

  const loadFolders = useCallback(async () => {
    setLoadingFolders(true);
    try {
      const list = await listDomainFolders({ with_counts: true });
      setFolders(list);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    } finally {
      setLoadingFolders(false);
    }
  }, [t]);

  // ---- list fetch ----
  //
  // Latest-wins token: if the user types fast, several fetches may be
  // in flight; only the most recent should set state. Same pattern as
  // the combobox.
  const [fetchToken, setFetchToken] = useState(0);
  const loadList = useCallback(async () => {
    const token = fetchToken + 1;
    setFetchToken(token);
    setLoadingList(true);
    try {
      // Root view ("all" scope) filters to domains NOT in any folder.
      // The backend's "root" sentinel is the no-folder filter, and
      // collapsing "all" onto it matches the principle now used on
      // /library and /prompts: items inside a folder only appear when
      // you navigate INTO that folder. Without this, a domain moved
      // into a folder still cluttered the root list.
      const folder_id = typeof scope === "number" ? scope : "root";
      const r = await listDomainsPicker({
        q: debouncedQuery,
        folder_id,
        page,
        page_size: pageSize,
      });
      setPickerData(r);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    } finally {
      setLoadingList(false);
    }
    // fetchToken is intentionally not a dep — we only want the token
    // captured at call-time, not a refetch when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, debouncedQuery, page, pageSize, t]);

  useEffect(() => {
    if (!isAuthorized) return;
    void loadFolders();
  }, [isAuthorized, loadFolders]);

  useEffect(() => {
    if (!isAuthorized) return;
    void loadList();
  }, [isAuthorized, loadList]);

  if (authLoading || !user || !isAuthorized) return null;

  const items = pickerData?.items ?? [];
  const total = pickerData?.total ?? 0;
  const hasMore = pickerData?.has_more ?? false;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // -------- modal helpers --------

  function afterDomainSaved(_d: Domain) {
    void loadList();
    void loadFolders();
    setModal({ kind: "closed" });
  }

  async function onEditClick(id: number) {
    // The list shows the lite picker shape; the edit modal needs the
    // full Domain (publish_config / custom_config). Brief load is
    // ~50ms on local Postgres — fine to keep the click flow simple.
    setEditLoadingId(id);
    try {
      const d = await getDomain(id);
      setModal({ kind: "edit", domain: d });
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    } finally {
      setEditLoadingId(null);
    }
  }

  async function onDelete(target: DomainPickerItem) {
    if (!confirm(t("domains.confirmDelete", { name: target.name }))) return;
    try {
      await deleteDomain(target.id);
      // Drop from selection if present, then refetch.
      setSelectedIds((s) => {
        if (!s.has(target.id)) return s;
        const next = new Set(s);
        next.delete(target.id);
        return next;
      });
      void loadList();
      void loadFolders();
      await refreshTrashCount();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        alert(err.message || t("domains.deleteBlockedInflight"));
      } else {
        alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
      }
    }
  }

  async function onTest(target: DomainPickerItem) {
    setTesting((s) => new Set(s).add(target.id));
    try {
      const r = await testDomain(target.id);
      setTestResults((m) => ({ ...m, [target.id]: r }));
    } catch (err) {
      setTestResults((m) => ({
        ...m,
        [target.id]: {
          ok: false,
          status_code: null,
          detail: err instanceof ApiError ? err.message : t("domains.testFailed"),
          elapsed_ms: null,
        },
      }));
    } finally {
      setTesting((s) => {
        const next = new Set(s);
        next.delete(target.id);
        return next;
      });
    }
  }

  // -------- folder operations --------

  async function onCreateFolder(parentId: number | null) {
    const name = window.prompt(t("domainFolders.namePrompt"));
    if (!name || !name.trim()) return;
    try {
      const created = await createDomainFolder({
        name: name.trim(),
        parent_id: parentId,
      });
      setFolders((arr) => [...arr, { ...created, domain_count: 0, subfolder_count: 0 }]);
      setScope(created.id);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.createFailed"));
    }
  }

  async function onRenameFolder(folder: DomainFolder) {
    const name = window.prompt(t("domainFolders.renamePrompt"), folder.name);
    if (!name || !name.trim() || name.trim() === folder.name) return;
    try {
      const updated = await updateDomainFolder(folder.id, { name: name.trim() });
      setFolders((arr) => arr.map((f) => (f.id === updated.id ? { ...f, name: updated.name } : f)));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.saveFailed"));
    }
  }

  async function onDeleteFolder(folder: DomainFolder) {
    if (!confirm(t("domainFolders.confirmDelete", { name: folder.name }))) return;
    try {
      await deleteDomainFolder(folder.id);
      setFolders((arr) => arr.filter((f) => f.id !== folder.id));
      if (scope === folder.id) {
        setScope(folder.parent_id ?? "all");
      }
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  async function onConfirmMove(folderId: number | null) {
    if (selectedIds.size === 0) return;
    setMoving(true);
    try {
      await bulkMoveDomains({
        domain_ids: Array.from(selectedIds),
        folder_id: folderId,
      });
      void loadList();
      void loadFolders();
      setSelectedIds(new Set());
      setModal({ kind: "closed" });
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setMoving(false);
    }
  }

  // Bulk-trash flow: confirm → POST /domains/bulk-trash → refresh +
  // surface partial-success info. The endpoint returns 200 even when
  // some rows are blocked (active bulk publish runs), so we always
  // refresh and just describe what happened.
  async function onBulkDelete() {
    if (selectedIds.size === 0 || deleting) return;
    if (!confirm(t("domains.confirmBulkDelete", { count: selectedIds.size }))) return;
    setDeleting(true);
    try {
      const result = await bulkTrashDomains({
        domain_ids: Array.from(selectedIds),
      });
      // Always refresh, even with zero trashed — folder counts may have
      // changed in some other tab and we'd rather over-fetch than show
      // a stale row.
      void loadList();
      void loadFolders();
      await refreshTrashCount();
      // Clear only the ids that actually moved; leave blocked ids
      // selected so the user can see them and re-attempt after fixing
      // the blocker (e.g. cancelling the active bulk publish run).
      if (result.blocked.length === 0) {
        setSelectedIds(new Set());
      } else {
        const blockedIds = new Set(result.blocked.map((b) => b.id));
        setSelectedIds((s) => {
          const next = new Set<number>();
          for (const id of s) if (blockedIds.has(id)) next.add(id);
          return next;
        });
        const sample = result.blocked
          .slice(0, 3)
          .map((b) => `• ${b.name ?? `#${b.id}`}: ${b.reason}`)
          .join("\n");
        const more =
          result.blocked.length > 3
            ? `\n…and ${result.blocked.length - 3} more.`
            : "";
        alert(
          t("domains.bulkDeletePartial", {
            trashed: result.trashed,
            blocked: result.blocked.length,
          }) + "\n\n" + sample + more,
        );
      }
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  }

  // "Select all N matching" — expands the current selection to every
  // row that matches the active filter (folder + search + cms_type).
  // Backend caps the result at 50k; we surface that 400 as-is.
  async function onSelectAllMatching() {
    if (selectingAll) return;
    setSelectingAll(true);
    try {
      // Same scope→folder_id mapping as loadList — keep them in lock-
      // step so the bulk-select cap matches what's actually rendered.
      const folder_id = typeof scope === "number" ? scope : "root";
      const { ids } = await listDomainsPickerIds({
        q: debouncedQuery,
        folder_id,
      });
      setSelectedIds(new Set(ids));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.failedToLoad"));
    } finally {
      setSelectingAll(false);
    }
  }

  // -------- selection --------

  function toggleSelect(id: number) {
    setSelectedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // "Select all" applies to the current page only — clicking it adds
  // every visible row id to the selection, or removes them if all
  // visible are already selected. Selection from other pages is
  // preserved.
  const allOnPageSelected =
    items.length > 0 && items.every((it) => selectedIds.has(it.id));

  function toggleSelectAllOnPage() {
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

  // Folder-name lookup for the small "in <folder>" badge on rows when
  // viewing the "All domains" scope (where rows can come from any
  // folder, so the placement is non-obvious).
  const folderNameById = useMemo(() => {
    const m = new Map<number, string>();
    for (const f of folders) m.set(f.id, f.name);
    return m;
  }, [folders]);

  return (
    <main className="w-full px-5 py-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("domains.title")}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            {t("domains.subtitle")}
          </p>
        </div>
        <div className="flex gap-2">
          {trashCount > 0 && (
            <Link
              href="/publish/domains/trash"
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              {t("domains.trashLinkWithCount", { count: trashCount })}
            </Link>
          )}
          <button
            onClick={() => void onCreateFolder(scope === "all" || scope === "root" ? null : scope)}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("domainFolders.newFolderButton")}
          </button>
          <button
            onClick={() => setModal({ kind: "import" })}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("domains.import")}
          </button>
          <button
            onClick={() => setModal({ kind: "importJson" })}
            title={t("domains.importJsonHint")}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("domains.importJson")}
          </button>
          <button
            onClick={() => setModal({ kind: "create" })}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            {t("domains.add")}
          </button>
        </div>
      </div>

      {loadError && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      )}

      <section className="min-w-0">
        <DomainBreadcrumb folders={folders} selected={scope} onSelect={setScope} />

        {/* Folder cards — library-style. At "all"/"root" scope we render
            every top-level folder; inside a specific folder we render
            its immediate subfolders. This replaces the persistent left
            sidebar tree: folder navigation is now visual, and goes one
            level at a time via the breadcrumb. Hidden entirely when
            there are no relevant folders to show. */}
        {(() => {
          const visibleFolders =
            typeof scope === "number"
              ? folders.filter((f) => f.parent_id === scope)
              : folders.filter((f) => f.parent_id === null);
          if (visibleFolders.length === 0) return null;
          const headingKey =
            typeof scope === "number"
              ? "domainFolders.subfoldersHeading"
              : "domainFolders.foldersHeading";
          return (
            <div className="mb-4">
              <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t(headingKey)} ({visibleFolders.length})
              </h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {visibleFolders.map((f) => (
                  <DomainFolderCard
                    key={f.id}
                    folder={f}
                    onOpen={() => setScope(f.id)}
                    onRename={() => void onRenameFolder(f)}
                    onDelete={() => void onDeleteFolder(f)}
                  />
                ))}
              </div>
              {loadingFolders && (
                <p className="mt-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                  {t("common.loading")}
                </p>
              )}
            </div>
          );
        })()}

          {/* Search bar — debounced 200 ms server-side so even a 50k-row
              account can type without blocking. */}
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="flex flex-1 items-center gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t("domains.searchPlaceholder")}
                className="block w-full max-w-md rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
              {loadingList && (
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  {t("common.loading")}
                </span>
              )}
            </div>
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {t("domains.totalCount", { count: total })}
            </span>
          </div>

          {/* Bulk-action bar — appears only when ≥ 1 row is selected.
              Selection persists across pages: the count here is the
              full selection, not just "on this page". */}
          {selectedIds.size > 0 && (
            <div className="mb-2 space-y-1">
              <div className="flex items-center justify-between rounded-md border border-neutral-300 bg-neutral-50 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900">
                <span className="text-neutral-700 dark:text-neutral-300">
                  {t("domains.selectedCount", { count: selectedIds.size })}
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
                    onClick={() => setModal({ kind: "move" })}
                    className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                  >
                    {t("domains.moveToFolder")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void onBulkDelete()}
                    disabled={deleting}
                    className="rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50 hover:bg-red-700"
                  >
                    {deleting
                      ? t("common.loading")
                      : t("domains.bulkDelete")}
                  </button>
                </div>
              </div>

              {/* "Select all N matching" — Gmail-style. Shows only when:
                  - the whole current page is selected
                  - selection size is still < total matching
                  - we're not already showing the user the whole world
                    (no point offering when selection = total). */}
              {selectedIds.size > 0 &&
                items.length > 0 &&
                items.every((it) => selectedIds.has(it.id)) &&
                selectedIds.size < total && (
                  <div className="rounded-md bg-blue-50 px-3 py-1.5 text-xs text-blue-800 dark:bg-blue-950/30 dark:text-blue-300">
                    {t("domains.selectAllMatchingPrompt", {
                      shown: selectedIds.size,
                      total,
                    })}{" "}
                    <button
                      type="button"
                      onClick={() => void onSelectAllMatching()}
                      disabled={selectingAll}
                      className="font-medium underline disabled:opacity-50"
                    >
                      {selectingAll
                        ? t("common.loading")
                        : t("domains.selectAllMatchingAction", { total })}
                    </button>
                  </div>
                )}
            </div>
          )}

          {/* `overflow-x-auto` (not `overflow-hidden`): when the viewport is
              narrower than the table's content width — happens on ~1280px
              laptops once you have the checkbox + 7 data columns + the
              edit/delete column — the user can horizontally scroll instead
              of having the rightmost Edit / Delete column silently clipped
              off-screen. `overflow-hidden` was hiding them entirely on
              narrow viewports. The rounded corners still work fine with
              `auto` because the container itself stays inside its border. */}
          <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
            <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
              <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  <th className="w-8 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={allOnPageSelected}
                      onChange={toggleSelectAllOnPage}
                      aria-label={t("common.selectAll")}
                    />
                  </th>
                  <th className="px-3 py-2">{t("domains.colName")}</th>
                  <th className="px-3 py-2">{t("domains.colBaseUrl")}</th>
                  <th className="px-3 py-2">{t("domains.colCms")}</th>
                  <th className="px-3 py-2">{t("domains.colAuth")}</th>
                  <th className="px-3 py-2">{t("domains.colLanguages")}</th>
                  <th className="px-3 py-2">{t("domains.colPlugin")}</th>
                  <th className="px-3 py-2">{t("domains.colTest")}</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
                {pickerData === null && (
                  <tr>
                    <td colSpan={9} className="px-3 py-8 text-center text-neutral-500">
                      {t("common.loading")}
                    </td>
                  </tr>
                )}
                {pickerData !== null && items.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-3 py-8 text-center text-neutral-500">
                      {debouncedQuery
                        ? t("domains.emptySearch", { q: debouncedQuery })
                        : t("domains.empty")}
                    </td>
                  </tr>
                )}
                {items.map((d) => {
                  const tr = testResults[d.id];
                  const isChecked = selectedIds.has(d.id);
                  const folderName =
                    scope === "all" && d.folder_id != null
                      ? folderNameById.get(d.folder_id)
                      : undefined;
                  return (
                    <tr
                      key={d.id}
                      className={
                        "hover:bg-neutral-50 dark:hover:bg-neutral-800/50 " +
                        (isChecked ? "bg-neutral-50 dark:bg-neutral-800/30" : "")
                      }
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelect(d.id)}
                          aria-label={t("domains.selectRow", { name: d.name })}
                        />
                      </td>
                      <td className="px-3 py-2 font-medium text-neutral-900 dark:text-neutral-100">
                        {d.name}
                        {folderName && (
                          <span className="ml-2 text-[10px] font-normal text-neutral-500">
                            {t("domains.inFolder", { folder: folderName })}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                        {d.base_url}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={
                            "inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset " +
                            (d.cms_type === "wordpress"
                              ? "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30"
                              : "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30")
                          }
                        >
                          {d.cms_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                        {d.auth_type}
                        {!d.has_credentials && (
                          <span className="ml-1 text-neutral-500">{t("domains.noCreds")}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                        {d.languages.join(", ")}
                      </td>
                      <td className="px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                        {d.cms_type === "wordpress" ? d.multilingual_plugin : "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => onTest(d)}
                            disabled={testing.has(d.id)}
                            className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
                          >
                            {testing.has(d.id) ? t("domains.testing") : t("domains.testButton")}
                          </button>
                          {tr && (
                            <span
                              title={tr.detail}
                              className={
                                "text-xs " +
                                (tr.ok
                                  ? "text-green-700 dark:text-green-400"
                                  : "text-red-700 dark:text-red-400")
                              }
                            >
                              {tr.ok ? "✓" : "✗"} {tr.elapsed_ms != null ? `${tr.elapsed_ms}ms` : ""}
                            </span>
                          )}
                        </div>
                        {tr && !tr.ok && (
                          <p className="mt-0.5 max-w-xs truncate text-xs text-red-600 dark:text-red-400" title={tr.detail}>
                            {tr.detail}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-xs">
                        <button
                          onClick={() => void onEditClick(d.id)}
                          disabled={editLoadingId === d.id}
                          className="mr-3 text-neutral-700 hover:underline disabled:opacity-50 dark:text-neutral-300"
                        >
                          {editLoadingId === d.id ? t("common.loading") : t("common.edit")}
                        </button>
                        <button
                          onClick={() => onDelete(d)}
                          className="text-red-600 hover:underline dark:text-red-400"
                        >
                          {t("common.delete")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination footer. Hidden when the result fits on one
              page — no use of vertical space for a "page 1 of 1" line. */}
          {(total > pageSize || page > 1) && (
            <div className="mt-2 flex items-center justify-between text-xs text-neutral-600 dark:text-neutral-400">
              <div className="flex items-center gap-2">
                <span>{t("domains.pageSizeLabel")}</span>
                <select
                  value={pageSize}
                  onChange={(e) =>
                    setPageSize(
                      Number(e.target.value) as (typeof PAGE_SIZE_OPTIONS)[number],
                    )
                  }
                  className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-3">
                <span className="tabular-nums">
                  {t("domains.pageOfTotal", { page, total: totalPages })}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || loadingList}
                  className="rounded-md border border-neutral-300 px-2 py-0.5 disabled:opacity-40 dark:border-neutral-700"
                >
                  {t("common.prev")}
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!hasMore || loadingList}
                  className="rounded-md border border-neutral-300 px-2 py-0.5 disabled:opacity-40 dark:border-neutral-700"
                >
                  {t("common.next")}
                </button>
              </div>
            </div>
          )}
      </section>

      {modal.kind === "create" && (
        <DomainModal
          onClose={() => setModal({ kind: "closed" })}
          onSaved={afterDomainSaved}
          defaultFolderId={typeof scope === "number" ? scope : null}
        />
      )}
      {modal.kind === "edit" && (
        <DomainModal
          domain={modal.domain}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={afterDomainSaved}
        />
      )}
      {modal.kind === "import" && (
        <DomainCsvImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => {
            void loadList();
            void loadFolders();
          }}
        />
      )}
      {modal.kind === "importJson" && (
        <DomainJsonImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => {
            void loadList();
            void loadFolders();
          }}
        />
      )}
      {modal.kind === "move" && (
        <MoveToFolderModal
          folders={folders}
          selectedCount={selectedIds.size}
          onClose={() => setModal({ kind: "closed" })}
          onConfirm={(folderId) => void onConfirmMove(folderId)}
          busy={moving}
        />
      )}
    </main>
  );
}
