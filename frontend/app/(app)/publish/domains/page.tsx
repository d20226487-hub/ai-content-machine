"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { DomainCsvImportModal } from "@/components/DomainCsvImportModal";
import { DomainJsonImportModal } from "@/components/DomainJsonImportModal";
import { DomainModal } from "@/components/DomainModal";
import { DomainBreadcrumb } from "@/components/domains/DomainBreadcrumb";
import { DomainFolderSidebar } from "@/components/domains/DomainFolderSidebar";
import { MoveToFolderModal } from "@/components/domains/MoveToFolderModal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  bulkMoveDomains,
  createDomainFolder,
  deleteDomain,
  deleteDomainFolder,
  getDomainTrashCount,
  listDomainFolders,
  listDomains,
  testDomain,
  updateDomainFolder,
  type Domain,
  type DomainFolder,
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

export default function DomainsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const isAuthorized = user && ["admin", "manager"].includes(user.role.name);

  // URL state drives the folder scope. Back/forward and deep-links Just
  // Work because we never store this twice.
  const scope = useMemo(
    () => parseScope(searchParams.get("folder")),
    [searchParams],
  );

  function setScope(next: FolderScope) {
    const param = scopeToParam(next);
    const qs = param ? `?folder=${encodeURIComponent(param)}` : "";
    router.push(`/publish/domains${qs}`);
  }

  const [domains, setDomains] = useState<Domain[] | null>(null);
  const [folders, setFolders] = useState<DomainFolder[]>([]);
  const [loadingFolders, setLoadingFolders] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [testing, setTesting] = useState<Set<number>>(new Set());
  const [testResults, setTestResults] = useState<Record<number, TestConnectionResult>>({});
  const [trashCount, setTrashCount] = useState(0);
  // Bulk-select state for the "Move to folder…" action.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [moving, setMoving] = useState(false);

  const refreshTrashCount = useCallback(async () => {
    try {
      const { count } = await getDomainTrashCount();
      setTrashCount(count);
    } catch {
      // non-critical; the badge just won't show
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

  const loadDomains = useCallback(
    async (currentScope: FolderScope) => {
      try {
        const list = await listDomains(currentScope);
        setDomains(list);
        setLoadError(null);
        // Selection refers to ids; if the current selection contains
        // ids not in the new list (folder switch), drop them.
        setSelectedIds((s) => {
          const next = new Set<number>();
          for (const d of list) if (s.has(d.id)) next.add(d.id);
          return next;
        });
      } catch (err) {
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
      }
    },
    [t],
  );

  useEffect(() => {
    if (!isAuthorized) return;
    void loadFolders();
  }, [isAuthorized, loadFolders]);

  useEffect(() => {
    if (!isAuthorized) return;
    void loadDomains(scope);
  }, [isAuthorized, scope, loadDomains]);

  if (authLoading || !user || !isAuthorized) return null;

  // -------- modal helpers --------

  function upsert(d: Domain) {
    // After save, the domain may have been moved to a folder outside
    // the current scope. Refetch the domain list to keep the page
    // accurate; refetch folder counts because they're now stale.
    void loadDomains(scope);
    void loadFolders();
    setModal({ kind: "closed" });
  }

  async function onDelete(target: Domain) {
    if (!confirm(t("domains.confirmDelete", { name: target.name }))) return;
    try {
      await deleteDomain(target.id);
      setDomains((list) => (list ? list.filter((x) => x.id !== target.id) : list));
      void loadFolders(); // counts changed
      await refreshTrashCount();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        alert(err.message || t("domains.deleteBlockedInflight"));
      } else {
        alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
      }
    }
  }

  async function onTest(target: Domain) {
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
      // Optimistically push so the user sees their new folder
      // immediately; counts re-derive from `loadFolders`.
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
      // If we were viewing the now-deleted folder, hop up to its parent
      // (or "all" if it was top-level).
      if (scope === folder.id) {
        setScope(folder.parent_id ?? "all");
      }
    } catch (err) {
      // 400 with the friendly "non-empty" message is the most common case.
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
      void loadDomains(scope);
      void loadFolders();
      setSelectedIds(new Set());
      setModal({ kind: "closed" });
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.saveFailed"));
    } finally {
      setMoving(false);
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

  function toggleSelectAll() {
    if (!domains) return;
    setSelectedIds((s) => {
      if (s.size === domains.length) return new Set();
      return new Set(domains.map((d) => d.id));
    });
  }

  const allSelected = domains != null && domains.length > 0 && selectedIds.size === domains.length;

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
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

      <div className="flex gap-4">
        <DomainFolderSidebar
          folders={folders}
          selected={scope}
          onSelect={setScope}
          onCreate={onCreateFolder}
          onRename={onRenameFolder}
          onDelete={onDeleteFolder}
          reloading={loadingFolders}
        />

        <section className="min-w-0 flex-1">
          <DomainBreadcrumb folders={folders} selected={scope} onSelect={setScope} />

          {/* Bulk-action bar appears only when 1+ rows are selected. Kept
              outside the table so the count stays visible while scrolling. */}
          {selectedIds.size > 0 && (
            <div className="mb-2 flex items-center justify-between rounded-md border border-neutral-300 bg-neutral-50 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900">
              <span className="text-neutral-700 dark:text-neutral-300">
                {t("domains.selectedCount", { count: selectedIds.size })}
              </span>
              <div className="flex gap-2">
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
              </div>
            </div>
          )}

          <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
            <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
              <thead className="bg-neutral-50 dark:bg-neutral-900/50">
                <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  <th className="w-8 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleSelectAll}
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
                {domains === null && (
                  <tr>
                    <td colSpan={9} className="px-3 py-8 text-center text-neutral-500">
                      {t("common.loading")}
                    </td>
                  </tr>
                )}
                {domains !== null && domains.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-3 py-8 text-center text-neutral-500">
                      {t("domains.empty")}
                    </td>
                  </tr>
                )}
                {domains?.map((d) => {
                  const tr = testResults[d.id];
                  const isChecked = selectedIds.has(d.id);
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
                          onClick={() => setModal({ kind: "edit", domain: d })}
                          className="mr-3 text-neutral-700 hover:underline dark:text-neutral-300"
                        >
                          {t("common.edit")}
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
        </section>
      </div>

      {modal.kind === "create" && (
        <DomainModal
          onClose={() => setModal({ kind: "closed" })}
          onSaved={upsert}
        />
      )}
      {modal.kind === "edit" && (
        <DomainModal
          domain={modal.domain}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={upsert}
        />
      )}
      {modal.kind === "import" && (
        <DomainCsvImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => {
            void loadDomains(scope);
            void loadFolders();
          }}
        />
      )}
      {modal.kind === "importJson" && (
        <DomainJsonImportModal
          onClose={() => setModal({ kind: "closed" })}
          onImported={() => {
            void loadDomains(scope);
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
