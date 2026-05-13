"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  permanentlyDeleteTable,
  previewTrashedTable,
  restoreTable,
} from "@/lib/library";
import type { BulkTable } from "@/lib/types";

/**
 * Read-only preview of a trashed bulk table.
 *
 * Renders a plain HTML table — not the editor grid — because we
 * deliberately don't load the editor's writable code path for a row that
 * isn't editable. Limited to the first 100 rows by client-side slicing so
 * a large trashed table doesn't blow up the page on a hover-click.
 */
const PREVIEW_ROW_LIMIT = 100;

export default function TrashPreviewPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const id = Number(params.id);

  const [table, setTable] = useState<BulkTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    previewTrashedTable(id)
      .then(setTable)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      );
  }, [id, t]);

  async function onRestore() {
    setBusy(true);
    try {
      await restoreTable(id);
      router.push(`/library/${id}`);
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
      setBusy(false);
    }
  }

  async function onDeletePermanent() {
    if (!table) return;
    if (!confirm(t("library.trash.confirmDeletePermanent", { name: table.name }))) return;
    setBusy(true);
    try {
      await permanentlyDeleteTable(id);
      router.push("/library/trash");
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
      setBusy(false);
    }
  }

  if (error) {
    return (
      <main className="mx-auto max-w-7xl px-5 py-6">
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      </main>
    );
  }

  if (!table) {
    return (
      <main className="mx-auto max-w-7xl px-5 py-6 text-sm text-neutral-500">
        {t("common.loading")}
      </main>
    );
  }

  const visibleRows = table.rows.slice(0, PREVIEW_ROW_LIMIT);
  const cellLookup = new Map<string, string | null>(
    table.cells.map((c) => [`${c.row_id}:${c.column_id}`, c.value]),
  );

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-1 text-xs">
        <Link
          href="/library/trash"
          className="text-neutral-500 hover:text-neutral-900 hover:underline dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          {t("library.trash.previewBack")}
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {table.name}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            {t("libraryTable.tableMeta", {
              cols: table.columns.length,
              rows: table.rows.length,
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRestore}
            disabled={busy}
            className="rounded-md border border-neutral-900 bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("library.trash.restore")}
          </button>
          {/* Restore is the primary CTA (solid dark button above); this
              destructive action is intentionally a quiet text link so the
              eye doesn't land on it first. */}
          <button
            type="button"
            onClick={onDeletePermanent}
            disabled={busy}
            className="px-2 py-1.5 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
          >
            {t("library.trash.deletePermanent")}
          </button>
        </div>
      </div>

      {/* Trashed banner */}
      <div className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
        {t("library.trash.previewBanner", {
          time: table.deleted_at ? new Date(table.deleted_at).toLocaleString() : "",
        })}
      </div>

      {/* Read-only data grid */}
      <div className="overflow-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full text-sm">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2 w-10">#</th>
              {table.columns.map((c) => (
                <th key={c.id} className="px-3 py-2">
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {visibleRows.map((row, i) => (
              <tr key={row.id} className="align-top">
                <td className="px-3 py-2 text-xs text-neutral-500">{i + 1}</td>
                {table.columns.map((col) => {
                  const v = cellLookup.get(`${row.id}:${col.id}`) ?? "";
                  return (
                    <td
                      key={col.id}
                      className="px-3 py-2 text-neutral-800 dark:text-neutral-200"
                    >
                      <div className="max-w-md whitespace-pre-wrap break-words">
                        {v}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {table.rows.length > PREVIEW_ROW_LIMIT && (
          <p className="border-t border-neutral-200 px-3 py-2 text-xs text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
            {t("common.showingRange", {
              from: 1,
              to: PREVIEW_ROW_LIMIT,
              total: table.rows.length,
            })}
          </p>
        )}
      </div>
    </main>
  );
}
