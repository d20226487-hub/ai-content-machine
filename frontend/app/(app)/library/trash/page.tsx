"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { UserChip } from "@/components/UserChip";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  bulkPermanentlyDelete,
  bulkRestoreTrash,
  emptyTrash,
  getTrashRetention,
  listTrash,
  permanentlyDeleteTable,
  restoreTable,
  type TrashRetention,
} from "@/lib/library";
import type { BulkTableListItem } from "@/lib/types";

const PAGE_SIZE = 50;

export default function LibraryTrashPage() {
  const { t } = useT();

  const [items, setItems] = useState<BulkTableListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [retention, setRetention] = useState<TrashRetention | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await listTrash({ page, page_size: PAGE_SIZE });
      setItems(r.items);
      setTotal(r.total);
      // Drop any selected ids that are no longer in this page (restore/delete
      // happened, or pagination moved). Keeps the bulk-action header in sync.
      setSelected((cur) => {
        const onPage = new Set(r.items.map((i) => i.id));
        const next = new Set<number>();
        for (const id of cur) if (onPage.has(id)) next.add(id);
        return next;
      });
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
    }
  }, [page, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    getTrashRetention()
      .then(setRetention)
      .catch(() => {
        // non-critical — header just won't show retention info
      });
  }, []);

  const allOnPageSelected = useMemo(
    () => items !== null && items.length > 0 && items.every((i) => selected.has(i.id)),
    [items, selected],
  );

  function toggleSelectAll() {
    if (!items) return;
    if (allOnPageSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((i) => i.id)));
    }
  }

  function toggleOne(id: number) {
    setSelected((cur) => {
      const n = new Set(cur);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function onRestore(id: number) {
    setBusy(true);
    try {
      await restoreTable(id);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onDeletePermanent(item: BulkTableListItem) {
    if (!confirm(t("library.trash.confirmDeletePermanent", { name: item.name }))) return;
    setBusy(true);
    try {
      await permanentlyDeleteTable(item.id);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onBulkRestore() {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      const { restored } = await bulkRestoreTrash(Array.from(selected));
      alert(t("library.trash.restored", { count: restored }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onBulkDelete() {
    if (selected.size === 0) return;
    if (!confirm(t("library.trash.confirmDeleteSelected", { count: selected.size }))) return;
    setBusy(true);
    try {
      const { deleted } = await bulkPermanentlyDelete(Array.from(selected));
      alert(t("library.trash.deleted", { count: deleted }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onEmptyTrash() {
    if (!confirm(t("library.trash.confirmEmpty", { count: total }))) return;
    setBusy(true);
    try {
      const { deleted } = await emptyTrash();
      alert(t("library.trash.deleted", { count: deleted }));
      setPage(1);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  const subtitle = retention
    ? retention.days > 0
      ? t("library.trash.subtitle", { days: retention.days })
      : t("library.trash.subtitleManual")
    : "";
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <main className="mx-auto max-w-6xl p-6">
      <div className="mb-1 text-xs">
        <Link
          href="/library"
          className="text-neutral-500 hover:text-neutral-900 hover:underline dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          ← {t("library.breadcrumbRoot")}
        </Link>
      </div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("library.trash.title")}
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {subtitle}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {selected.size > 0 && (
            <>
              <button
                type="button"
                onClick={onBulkRestore}
                disabled={busy}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("library.trash.restoreSelected")} ({selected.size})
              </button>
              {/* Destructive — kept as quiet text link, not a bordered CTA,
                  so it doesn't invite a click. Restore is the primary action;
                  this is the "and if you really mean it" fallback. */}
              <button
                type="button"
                onClick={onBulkDelete}
                disabled={busy}
                className="px-2 py-1 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
              >
                {t("library.trash.deleteSelected")} ({selected.size})
              </button>
            </>
          )}
          {total > 0 && (
            <button
              type="button"
              onClick={onEmptyTrash}
              disabled={busy}
              className="px-2 py-1 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
            >
              {t("library.trash.emptyAll")}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {items === null && (
        <p className="text-sm text-neutral-500">{t("common.loading")}</p>
      )}

      {items !== null && items.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
          {t("library.trash.empty")}
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="divide-y divide-neutral-200 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
          <li className="flex items-center gap-3 bg-neutral-50 px-5 py-2 text-xs text-neutral-600 dark:bg-neutral-900/50 dark:text-neutral-400">
            <input
              type="checkbox"
              checked={allOnPageSelected}
              onChange={toggleSelectAll}
              className="h-3.5 w-3.5"
              aria-label={t("library.trash.selectAll")}
            />
            <span>{t("library.trash.selectAll")}</span>
          </li>
          {items.map((tab) => (
            <li
              key={tab.id}
              className="flex items-start gap-3 px-5 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
            >
              <input
                type="checkbox"
                checked={selected.has(tab.id)}
                onChange={() => toggleOne(tab.id)}
                className="mt-1 h-3.5 w-3.5"
              />
              <div className="min-w-0 flex-1">
                <Link
                  href={`/library/trash/${tab.id}`}
                  className="block truncate text-sm font-medium text-neutral-900 hover:underline dark:text-neutral-100"
                >
                  {tab.name}
                </Link>
                <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                  {t("library.tableMeta", {
                    cols: tab.column_count,
                    rows: tab.row_count,
                    time: new Date(tab.updated_at).toLocaleDateString(),
                  })}
                </p>
                <p className="mt-0.5 text-[11px] text-neutral-400 dark:text-neutral-500">
                  {tab.deleted_at &&
                    t("library.trash.deletedAt", {
                      time: new Date(tab.deleted_at).toLocaleString(),
                    })}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                {tab.created_by_name && <UserChip name={tab.created_by_name} />}
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <Link
                    href={`/library/trash/${tab.id}`}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("library.trash.preview")}
                  </Link>
                  <button
                    type="button"
                    onClick={() => onRestore(tab.id)}
                    disabled={busy}
                    className="font-medium text-neutral-700 hover:underline disabled:opacity-50 dark:text-neutral-300"
                  >
                    {t("library.trash.restore")}
                  </button>
                  {/* Per-row destructive — quieter than Restore so the eye
                      lands on the safe action first. */}
                  <button
                    type="button"
                    onClick={() => onDeletePermanent(tab)}
                    disabled={busy}
                    className="text-red-500/60 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
                  >
                    {t("library.trash.deletePermanent")}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Pagination footer */}
      {items && total > PAGE_SIZE && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-neutral-600 dark:text-neutral-400">
          <span>
            {t("common.showingRange", {
              from: (page - 1) * PAGE_SIZE + 1,
              to: Math.min(page * PAGE_SIZE, total),
              total,
            })}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("common.prev")}
            </button>
            <span>{t("common.pageXslashY", { page, total: totalPages })}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page * PAGE_SIZE >= total}
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
