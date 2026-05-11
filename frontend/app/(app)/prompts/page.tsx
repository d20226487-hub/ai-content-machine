"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { NewPromptModal } from "@/components/NewPromptModal";
import { TestPromptModal } from "@/components/TestPromptModal";
import { UserChip } from "@/components/UserChip";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  createCategory,
  deleteCategory,
  getPrompt,
  listCategories,
  listPrompts,
  listTags,
  renameCategory,
  updatePromptMeta,
} from "@/lib/prompts";
import type {
  Category,
  PromptDetail,
  PromptListItem,
  Tag,
} from "@/lib/types";

export default function PromptsPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const { t } = useT();

  // ---- URL-driven state ----
  const folder = sp.get("folder") ? Number(sp.get("folder")) : null;
  const tagIds = useMemo(
    () => parseTagIds(sp.get("tags")),
    [sp],
  );
  const q = sp.get("q") ?? "";
  const page = Number(sp.get("page") ?? "1");
  const pageSize = Number(sp.get("size") ?? "50");
  const includeDescendants = sp.get("subs") === "true";

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
    const path = `/prompts${qs ? "?" + qs : ""}`;
    if (opts.push) router.push(path);
    else router.replace(path);
  }

  // ---- Server data ----
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [prompts, setPrompts] = useState<PromptListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  // ---- Local UI state ----
  const [searchDraft, setSearchDraft] = useState(q);
  const [debouncedSearch, setDebouncedSearch] = useState(q);
  const [refreshTick, setRefreshTick] = useState(0);
  const [testingPrompt, setTestingPrompt] = useState<PromptDetail | null>(null);
  const [testLoadingId, setTestLoadingId] = useState<number | null>(null);

  async function onOpenTest(promptId: number) {
    setTestLoadingId(promptId);
    try {
      const detail = await getPrompt(promptId);
      setTestingPrompt(detail);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("prompts.failedLoadPrompts"));
    } finally {
      setTestLoadingId(null);
    }
  }

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

  const refreshCategories = useCallback(async () => {
    try {
      const cs = await listCategories({ with_counts: true });
      setCategories(cs);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("prompts.failedLoadFolders"));
    }
  }, [t]);

  useEffect(() => {
    void refreshCategories();
    listTags()
      .then(setTags)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("prompts.failedLoadTags")),
      );
  }, [refreshCategories, t]);

  useEffect(() => {
    setPrompts(null);
    const categoryParam = folder;

    listPrompts({
      category_id: categoryParam,
      include_descendants: folder !== null && includeDescendants,
      tag_ids: tagIds,
      q,
      page,
      page_size: pageSize,
    })
      .then((r) => {
        setPrompts(r.items);
        setTotal(r.total);
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("prompts.failedLoadPrompts")),
      );
  }, [folder, tagIds, q, page, pageSize, includeDescendants, refreshTick, t]);

  // ---- Folder helpers ----
  const folderById = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories],
  );

  const breadcrumb = useMemo(() => {
    if (folder === null) return [];
    const path: Category[] = [];
    let cur: Category | undefined = folderById.get(folder);
    while (cur) {
      path.unshift(cur);
      cur = cur.parent_id != null ? folderById.get(cur.parent_id) : undefined;
    }
    return path;
  }, [folder, folderById]);

  const childFolders = useMemo(
    () => categories.filter((c) => c.parent_id === folder),
    [categories, folder],
  );

  function navigateFolder(id: number | null) {
    updateParams({ folder: id, page: null }, { push: true });
  }

  async function onCreateFolder() {
    const name = window.prompt(t("prompts.folderNamePrompt"));
    if (!name?.trim()) return;
    try {
      await createCategory(name.trim(), folder);
      await refreshCategories();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.createFailed"));
    }
  }

  async function onRenameFolder(cat: Category) {
    const name = window.prompt(t("prompts.renameFolderPrompt"), cat.name);
    if (!name?.trim() || name.trim() === cat.name) return;
    try {
      await renameCategory(cat.id, name.trim());
      await refreshCategories();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.renameFailed"));
    }
  }

  async function onDeleteFolder(cat: Category) {
    if (!window.confirm(t("prompts.confirmDeleteFolder", { name: cat.name }))) return;
    try {
      await deleteCategory(cat.id);
      await refreshCategories();
      if (folder === cat.id) navigateFolder(cat.parent_id);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  function toggleTag(id: number) {
    const set = new Set(tagIds);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    const next = Array.from(set);
    updateParams({ tags: next.length ? next.join(",") : null, page: null });
  }

  function clearTags() {
    updateParams({ tags: null, page: null });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <main className="mx-auto max-w-6xl p-6">
      {/* Toolbar — top row */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Breadcrumb
            path={breadcrumb}
            onJump={(id) => navigateFolder(id)}
            homeLabel={t("prompts.breadcrumbHome")}
          />
          <h1 className="mt-1 truncate text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {folder === null
              ? t("prompts.title")
              : folderById.get(folder)?.name ?? t("prompts.folderFallback")}
          </h1>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {folder !== null && (
            <label
              className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-400"
              title={t("prompts.includeSubfoldersHint")}
            >
              <input
                type="checkbox"
                checked={includeDescendants}
                onChange={(e) =>
                  updateParams({
                    subs: e.target.checked ? "true" : null,
                    page: null,
                  })
                }
                className="h-3.5 w-3.5"
              />
              {t("prompts.includeSubfolders")}
            </label>
          )}
          <button
            onClick={onCreateFolder}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("prompts.newFolder")}
          </button>
          <Link
            href="/prompts/tags"
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("prompts.manageTags")}
          </Link>
          <button
            onClick={() => setShowNew(true)}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("prompts.newPrompt")}
          </button>
        </div>
      </div>

      {/* Search + tag filter */}
      <div className="mt-5 flex flex-wrap items-start gap-4">
        <input
          type="text"
          placeholder={t("prompts.searchPlaceholder")}
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          className="block w-72 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />

        {tags.length > 0 && (
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
            <span className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("prompts.tagsLabel")}
            </span>
            {tags.map((tag) => {
              const on = tagIds.includes(tag.id);
              return (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => toggleTag(tag.id)}
                  className={
                    "rounded-full border px-2 py-0.5 text-xs font-medium transition " +
                    (on
                      ? "border-neutral-900 bg-neutral-900 text-white dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900"
                      : "border-neutral-300 text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800")
                  }
                  title={
                    on
                      ? t("prompts.tagRemoveFilter", { name: tag.name })
                      : t("prompts.tagAddFilter", { name: tag.name })
                  }
                >
                  {on && "✓ "}
                  {tag.name}
                </button>
              );
            })}
            {tagIds.length > 0 && (
              <button
                type="button"
                onClick={clearTags}
                className="text-xs text-neutral-500 underline hover:text-red-600 dark:text-neutral-400 dark:hover:text-red-400"
              >
                {t("prompts.tagsClear")}
              </button>
            )}
            {tagIds.length > 1 && (
              <span className="text-[11px] text-neutral-500 dark:text-neutral-400">
                {t("prompts.tagsAndNote")}
              </span>
            )}
          </div>
        )}
      </div>

      {loadError && (
        <p className="mt-6 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {/* Folders section */}
      {childFolders.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("prompts.foldersHeading", { count: childFolders.length })}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            {childFolders.map((c) => (
              <FolderCard
                key={c.id}
                cat={c}
                onOpen={() => navigateFolder(c.id)}
                onRename={() => onRenameFolder(c)}
                onDelete={() => onDeleteFolder(c)}
                renameLabel={t("common.rename")}
                deleteLabel={t("common.delete")}
                promptsCountLabel={t("prompts.folderPromptsCount", { count: c.prompt_count ?? 0 })}
                subfoldersCountLabel={
                  (c.subfolder_count ?? 0) > 0
                    ? t("prompts.folderSubfoldersCount", { count: c.subfolder_count ?? 0 })
                    : ""
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* Prompts section */}
      <section className="mt-6">
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("prompts.promptsHeading")} {total > 0 && `(${total})`}
        </h2>

        {!prompts && !loadError && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">{t("common.loading")}</p>
        )}

        {prompts && prompts.length === 0 && (
          <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
            {q || tagIds.length > 0
              ? t("prompts.empty.noMatches")
              : t("prompts.empty.none")}
            {!q && tagIds.length === 0 && (
              <button
                onClick={() => setShowNew(true)}
                className="ml-2 font-medium text-neutral-900 underline dark:text-neutral-100"
              >
                {t("prompts.empty.createFirst")}
              </button>
            )}
          </div>
        )}

        {prompts && prompts.length > 0 && (
          <ul className="divide-y divide-neutral-200 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
            {prompts.map((p) => (
              <li key={p.id} className="px-5 py-4 hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/prompts/${p.id}`}
                      title={p.name}
                      className="block truncate text-sm font-medium text-neutral-900 hover:underline dark:text-neutral-100"
                    >
                      {p.name}
                    </Link>
                    <p className="mt-1 line-clamp-2 font-mono text-xs text-neutral-500 dark:text-neutral-400">
                      {p.current_version?.content ?? t("prompts.unfilledVariablesPrompt")}
                    </p>
                    {folder === null &&
                      p.category_id &&
                      folderById.has(p.category_id) && (
                        <p className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                          {t("prompts.inFolderLabel")}{" "}
                          <button
                            type="button"
                            onClick={() => navigateFolder(p.category_id!)}
                            className="text-neutral-700 underline-offset-2 hover:underline dark:text-neutral-300"
                          >
                            {folderById.get(p.category_id!)!.name}
                          </button>
                        </p>
                      )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    {p.created_by_name && (
                      <UserChip name={p.created_by_name} />
                    )}
                    <p className="text-xs text-neutral-500 dark:text-neutral-400">
                      {t("prompts.versionPrefix")}{p.current_version?.version_number ?? "?"}
                    </p>
                    <p className="text-[11px] text-neutral-400 dark:text-neutral-500">
                      {new Date(p.updated_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                {p.tags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {p.tags.map((tag) => (
                      <span
                        key={tag.id}
                        className="rounded-full bg-neutral-100 px-2 py-0.5 text-[10px] font-medium text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                      >
                        {tag.name}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                  <Link
                    href={`/prompts/${p.id}`}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("common.open")}
                  </Link>
                  <button
                    type="button"
                    onClick={() => onOpenTest(p.id)}
                    disabled={testLoadingId === p.id}
                    title={t("promptDetail.testHint")}
                    className="font-medium text-neutral-700 hover:underline disabled:opacity-60 dark:text-neutral-300"
                  >
                    {testLoadingId === p.id
                      ? t("test.generating")
                      : t("promptDetail.test")}
                  </button>
                  <PromptMoveControl
                    prompt={p}
                    categories={categories}
                    moveLabel={t("common.move")}
                    noFolderLabel={t("prompts.movePickerNoFolder")}
                    onMove={async (catId) => {
                      try {
                        await updatePromptMeta(p.id, { category_id: catId });
                        setRefreshTick((n) => n + 1);
                        await refreshCategories();
                      } catch (err) {
                        alert(
                          err instanceof ApiError ? err.message : t("common.moveFailed"),
                        );
                      }
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Pagination footer */}
        {prompts && total > pageSize && (
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
                onClick={() =>
                  updateParams({ page: Math.max(1, page - 1) })
                }
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

      {showNew && (
        <NewPromptModal
          categories={categories}
          defaultCategoryId={folder}
          onClose={() => setShowNew(false)}
          onCreated={(p) => {
            setPrompts((cur) =>
              cur ? [{ ...mapDetailToListItem(p) }, ...cur] : cur,
            );
            setTotal((n) => n + 1);
            void refreshCategories();
          }}
        />
      )}

      {testingPrompt && (
        <TestPromptModal
          prompt={testingPrompt}
          onClose={() => setTestingPrompt(null)}
        />
      )}
    </main>
  );
}

// ---------------- helpers + sub-components ----------------

function parseTagIds(raw: string | null): number[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
}

function Breadcrumb({
  path,
  onJump,
  homeLabel,
}: {
  path: Category[];
  onJump: (id: number | null) => void;
  homeLabel: string;
}) {
  return (
    <nav className="flex flex-wrap items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
      <button
        type="button"
        onClick={() => onJump(null)}
        className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
      >
        {homeLabel}
      </button>
      {path.map((c, i) => (
        <span key={c.id} className="flex items-center gap-1">
          <span>/</span>
          {i === path.length - 1 ? (
            <span className="text-neutral-700 dark:text-neutral-300">{c.name}</span>
          ) : (
            <button
              type="button"
              onClick={() => onJump(c.id)}
              className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
            >
              {c.name}
            </button>
          )}
        </span>
      ))}
    </nav>
  );
}

function FolderCard({
  cat,
  onOpen,
  onRename,
  onDelete,
  renameLabel,
  deleteLabel,
  promptsCountLabel,
  subfoldersCountLabel,
}: {
  cat: Category;
  onOpen: () => void;
  onRename: () => void;
  onDelete: () => void;
  renameLabel: string;
  deleteLabel: string;
  promptsCountLabel: string;
  subfoldersCountLabel: string;
}) {
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
            {cat.name}
          </p>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {promptsCountLabel}
            {subfoldersCountLabel}
          </p>
        </div>
      </button>
      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRename();
          }}
          className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          title={renameLabel}
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
          title={deleteLabel}
        >
          {deleteLabel}
        </button>
      </div>
    </div>
  );
}

function PromptMoveControl({
  prompt,
  categories,
  moveLabel,
  noFolderLabel,
  onMove,
}: {
  prompt: PromptListItem;
  categories: Category[];
  moveLabel: string;
  noFolderLabel: string;
  onMove: (categoryId: number | null) => void | Promise<void>;
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
  const sorted = [...categories].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <span className="inline-flex items-center gap-1">
      <select
        autoFocus
        defaultValue={prompt.category_id ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          void onMove(v === "" ? null : Number(v));
          setOpen(false);
        }}
        onBlur={() => setOpen(false)}
        className="rounded-md border border-neutral-300 bg-white px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
      >
        <option value="">{noFolderLabel}</option>
        {sorted.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </span>
  );
}

function mapDetailToListItem(d: PromptDetail): PromptListItem {
  return {
    id: d.id,
    name: d.name,
    category_id: d.category_id,
    current_version: d.current_version,
    tags: d.tags,
    created_by_id: d.created_by_id,
    created_by_name: d.created_by_name,
    created_by_email: d.created_by_email,
    created_at: d.created_at,
    updated_at: d.updated_at,
  };
}
