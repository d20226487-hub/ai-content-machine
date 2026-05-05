"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  createTag,
  deleteTag,
  listTagsManage,
  mergeTag,
  renameTag,
  type TagWithStats,
} from "@/lib/prompts";

export default function TagsManagePage() {
  const { t } = useT();
  const [items, setItems] = useState<TagWithStats[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  const [mergingId, setMergingId] = useState<number | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState<number | null>(null);

  const [newName, setNewName] = useState("");

  useEffect(() => {
    const tm = setTimeout(() => setDebouncedSearch(search), 250);
    return () => clearTimeout(tm);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  async function refresh() {
    try {
      const r = await listTagsManage({ page, page_size: pageSize, q: debouncedSearch });
      setItems(r.items);
      setTotal(r.total);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("tags.failedLoad"));
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, debouncedSearch]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await createTag(name);
      setNewName("");
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.createFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmRename(id: number) {
    const name = renameDraft.trim();
    setRenamingId(null);
    if (!name) return;
    const cur = items?.find((tag) => tag.id === id);
    if (!cur || cur.name === name.toLowerCase()) return;
    setBusy(true);
    try {
      await renameTag(id, name);
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.renameFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(tag: TagWithStats) {
    const msg =
      tag.prompt_count > 0
        ? t("tags.confirmDeleteWithCount", { name: tag.name, count: tag.prompt_count })
        : t("tags.confirmDelete", { name: tag.name });
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      await deleteTag(tag.id);
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirmMerge(srcId: number) {
    if (mergeTargetId == null || mergeTargetId === srcId) {
      setMergingId(null);
      setMergeTargetId(null);
      return;
    }
    const src = items?.find((tag) => tag.id === srcId);
    const tgt = items?.find((tag) => tag.id === mergeTargetId);
    if (!src || !tgt) return;
    if (
      !window.confirm(
        t("tags.confirmMerge", {
          src: src.name,
          tgt: tgt.name,
          count: src.prompt_count,
        }),
      )
    ) {
      setMergingId(null);
      setMergeTargetId(null);
      return;
    }
    setBusy(true);
    try {
      await mergeTag(srcId, mergeTargetId);
      setMergingId(null);
      setMergeTargetId(null);
      await refresh();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.mergeFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-8">
      <div className="mb-2">
        <Link
          href="/prompts"
          className="text-xs text-neutral-500 hover:underline dark:text-neutral-400"
        >
          ← {t("nav.prompts")}
        </Link>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("tags.title")}
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("tags.subtitle")}
          </p>
        </div>

        <form onSubmit={onCreate} className="flex items-center gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t("tags.newPlaceholder")}
            className="block w-48 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          <button
            type="submit"
            disabled={busy || !newName.trim()}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("common.add")}
          </button>
        </form>
      </div>

      <div className="mt-5">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("tags.search")}
          className="block w-full max-w-sm rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </div>

      {error && (
        <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="mt-5 overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">{t("tags.colName")}</th>
              <th className="px-3 py-2">{t("tags.colPrompts")}</th>
              <th className="px-3 py-2">{t("tags.colLastUsed")}</th>
              <th className="px-3 py-2">{t("tags.colCreated")}</th>
              <th className="px-3 py-2 text-right">{t("common.actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {items === null && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-neutral-500">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {items !== null && items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-neutral-500">
                  {debouncedSearch ? t("tags.emptySearch") : t("tags.empty")}
                </td>
              </tr>
            )}
            {items?.map((tag) => {
              const isRenaming = renamingId === tag.id;
              const isMerging = mergingId === tag.id;
              const otherTags = items.filter((x) => x.id !== tag.id);
              return (
                <tr key={tag.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800/40">
                  <td className="px-3 py-2 align-middle">
                    {isRenaming ? (
                      <input
                        type="text"
                        autoFocus
                        value={renameDraft}
                        onChange={(e) => setRenameDraft(e.target.value)}
                        onBlur={() => onConfirmRename(tag.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") void onConfirmRename(tag.id);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        className="block w-48 rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                    ) : (
                      <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-xs font-medium text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                        {tag.name}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-middle text-neutral-700 dark:text-neutral-300">
                    {tag.prompt_count > 0 ? (
                      <Link
                        href={`/prompts?tag=${tag.id}`}
                        className="hover:underline"
                      >
                        {tag.prompt_count}
                      </Link>
                    ) : (
                      <span className="text-neutral-400">0</span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-middle text-xs text-neutral-500 dark:text-neutral-400">
                    {tag.last_used ? new Date(tag.last_used).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-3 py-2 align-middle text-xs text-neutral-500 dark:text-neutral-400">
                    {new Date(tag.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 align-middle text-right">
                    {isMerging ? (
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-xs text-neutral-500 dark:text-neutral-400">
                          {t("tags.mergeIntoLabel")}
                        </span>
                        <select
                          value={mergeTargetId ?? ""}
                          onChange={(e) =>
                            setMergeTargetId(e.target.value ? Number(e.target.value) : null)
                          }
                          className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200"
                        >
                          <option value="">{t("tags.mergePickTarget")}</option>
                          {otherTags.map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => onConfirmMerge(tag.id)}
                          disabled={busy || mergeTargetId == null}
                          className="rounded-md bg-neutral-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
                        >
                          {t("common.merge")}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMergingId(null);
                            setMergeTargetId(null);
                          }}
                          className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                        >
                          {t("common.cancel")}
                        </button>
                      </div>
                    ) : (
                      <div className="flex justify-end gap-3 text-xs">
                        <button
                          type="button"
                          onClick={() => {
                            setRenamingId(tag.id);
                            setRenameDraft(tag.name);
                          }}
                          className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                        >
                          {t("common.rename")}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setMergingId(tag.id);
                            setMergeTargetId(null);
                          }}
                          disabled={otherTags.length === 0}
                          className="font-medium text-neutral-700 hover:underline disabled:opacity-40 dark:text-neutral-300"
                          title={
                            otherTags.length === 0
                              ? t("tags.mergeNeedOther")
                              : undefined
                          }
                        >
                          {t("common.merge")}
                        </button>
                        <button
                          type="button"
                          onClick={() => onDelete(tag)}
                          className="font-medium text-red-600 hover:underline dark:text-red-400"
                        >
                          {t("common.delete")}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      {total > pageSize && (
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
                onChange={(e) => {
                  setPage(1);
                  setPageSize(Number(e.target.value));
                }}
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
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.prev")}
            </button>
            <span>{t("common.pageXslashY", { page, total: Math.max(1, Math.ceil(total / pageSize)) })}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * pageSize >= total}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.nextArrow")}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
