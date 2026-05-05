"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BulkTableGrid } from "@/components/BulkTableGrid";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useT } from "@/lib/i18n-context";
import {
  deleteTable,
  downloadCsv,
  duplicateTable,
  getTable,
  renameTable,
} from "@/lib/library";
import type { BulkTable } from "@/lib/types";

export default function LibraryTablePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const id = Number(params.id);

  const [table, setTable] = useState<BulkTable | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  const [saving, setSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<number | null>(null);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    getTable(id)
      .then(setTable)
      .catch((e) => {
        console.error("[LibraryTable] load failed", e);
        setError(e);
      });
  }, [id]);

  async function commitRename() {
    if (!table) return;
    const name = nameDraft.trim();
    setEditingName(false);
    if (!name || name === table.name) return;
    try {
      const updated = await renameTable(table.id, { name });
      setTable({ ...table, name: updated.name });
    } catch (e) {
      console.error("[LibraryTable] rename failed", e);
    }
  }

  async function onDuplicate() {
    if (!table) return;
    try {
      const dup = await duplicateTable(table.id);
      router.push(`/library/${dup.id}`);
    } catch (e) {
      console.error("[LibraryTable] duplicate failed", e);
    }
  }

  async function onDelete() {
    if (!table) return;
    if (!window.confirm(t("libraryTable.confirmDelete", { name: table.name }))) return;
    try {
      await deleteTable(table.id);
      router.replace("/library");
    } catch (e) {
      console.error("[LibraryTable] delete failed", e);
    }
  }

  async function onExport() {
    if (!table) return;
    try {
      await downloadCsv(table.id, `${table.name}.csv`);
    } catch (e) {
      console.error("[LibraryTable] export failed", e);
    }
  }

  if (error) {
    return (
      <main className="mx-auto max-w-5xl p-8">
        <Link
          href="/library"
          className="text-sm text-neutral-500 hover:underline dark:text-neutral-400"
        >
          {t("libraryTable.back")}
        </Link>
        <div className="mt-6">
          <ErrorPanel title={t("libraryTable.failedLoad")} error={error} />
        </div>
      </main>
    );
  }

  if (!table) {
    return (
      <main className="mx-auto max-w-5xl p-8 text-sm text-neutral-500 dark:text-neutral-400">
        {t("common.loading")}
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            href="/library"
            className="text-xs text-neutral-500 hover:underline dark:text-neutral-400"
          >
            {t("libraryTable.back")}
          </Link>
          <div className="mt-1 flex items-center gap-3">
            {editingName ? (
              <input
                type="text"
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void commitRename();
                  if (e.key === "Escape") setEditingName(false);
                }}
                className="block rounded-md border border-neutral-300 px-2 py-1 text-2xl font-semibold dark:border-neutral-700 dark:bg-neutral-900"
              />
            ) : (
              <h1
                onClick={() => {
                  setNameDraft(table.name);
                  setEditingName(true);
                }}
                className="cursor-pointer truncate text-2xl font-semibold text-neutral-900 hover:underline dark:text-neutral-100"
                title={t("libraryTable.clickToRename")}
              >
                {table.name}
              </h1>
            )}
            <SaveIndicator
              saving={saving}
              lastSaved={lastSaved}
              savingLabel={t("common.saving")}
              savedLabel={t("common.saved")}
              savedAtLabel={(time: string) => t("libraryTable.savedAt", { time })}
            />
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={onExport}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("libraryTable.exportCsv")}
          </button>
          <button
            onClick={onDuplicate}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("common.duplicate")}
          </button>
          <button
            onClick={onDelete}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-neutral-700 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            {t("common.delete")}
          </button>
        </div>
      </div>

      <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
        {t("libraryTable.tableMeta", { cols: table.columns.length, rows: table.rows.length })}
        {table.created_by_name && (
          <>
            {t("libraryTable.createdBy")}
            <span className="text-neutral-700 dark:text-neutral-300">
              {table.created_by_name}
            </span>
          </>
        )}
      </p>

      <div className="mt-6">
        <BulkTableGrid
          table={table}
          onTableChange={setTable}
          onSavingChange={(s, ts) => {
            setSaving(s);
            if (ts) setLastSaved(ts);
          }}
        />
      </div>
    </main>
  );
}

function SaveIndicator({
  saving,
  lastSaved,
  savingLabel,
  savedLabel,
  savedAtLabel,
}: {
  saving: boolean;
  lastSaved: number | null;
  savingLabel: string;
  savedLabel: string;
  savedAtLabel: (time: string) => string;
}) {
  if (saving) {
    return (
      <span className="text-xs text-neutral-500 dark:text-neutral-400">{savingLabel}</span>
    );
  }
  if (lastSaved) {
    const ago = Math.max(0, Math.round((Date.now() - lastSaved) / 1000));
    const label =
      ago < 5
        ? savedLabel
        : savedAtLabel(new Date(lastSaved).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    return <span className="text-xs text-green-600 dark:text-green-400">{label}</span>;
  }
  return null;
}
