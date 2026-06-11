"use client";

import { ChangeEvent, FormEvent, useRef, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import { importCsv } from "@/lib/library";
import type { BulkTable } from "@/lib/types";

interface Props {
  onClose: () => void;
  /**
   * Called with the successfully created tables. ``navigate`` is true only
   * when exactly one file was imported (and it succeeded) — the page opens
   * that table. For a multi-file import it's false: the page just refreshes
   * its list and stays put.
   */
  onImported: (tables: BulkTable[], opts: { navigate: boolean }) => void;
  /** Land imported tables in this folder (null = root). */
  defaultFolderId?: number | null;
}

const SAMPLES: { file: string; labelKey: "csvImport.sampleWpSingle" | "csvImport.sampleWpMulti" | "csvImport.sampleCustomSingle" | "csvImport.sampleCustomMulti" }[] = [
  { file: "wordpress-single-site.csv", labelKey: "csvImport.sampleWpSingle" },
  { file: "wordpress-multi-site.csv", labelKey: "csvImport.sampleWpMulti" },
  { file: "custom-cms-single-site.csv", labelKey: "csvImport.sampleCustomSingle" },
  { file: "custom-cms-multi-site.csv", labelKey: "csvImport.sampleCustomMulti" },
];

/** Filename without its extension — used as the table name for each file. */
function tableNameForFile(f: File): string {
  return f.name.replace(/\.[^.]+$/, "").trim() || "Imported table";
}

export function ImportCsvModal({ onClose, onImported, defaultFolderId }: Props) {
  const { t } = useT();
  const [files, setFiles] = useState<File[]>([]);
  // Single-file imports keep an editable table name; multi-file imports name
  // each table after its file.
  const [name, setName] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [delimiter, setDelimiter] = useState(",");
  const [hasHeader, setHasHeader] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [sampleOpen, setSampleOpen] = useState(false);
  const sampleMenuRef = useRef<HTMLDivElement | null>(null);

  const single = files.length === 1;

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    if (picked.length === 0) return;
    setFiles(picked);
    setError(null);
    // Preview the first file only.
    setPreviewText(await picked[0].slice(0, 64 * 1024).text());
    if (picked.length === 1 && !name.trim()) {
      setName(tableNameForFile(picked[0]));
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    if (single && !name.trim()) return;

    setBusy(true);
    setError(null);
    setProgress({ done: 0, total: files.length });

    const created: BulkTable[] = [];
    const failed: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const tableName = single ? name.trim() : tableNameForFile(f);
      try {
        const table = await importCsv({
          name: tableName,
          file: f,
          delimiter,
          has_header: hasHeader,
          folder_id: defaultFolderId ?? null,
        });
        created.push(table);
      } catch (err) {
        console.error("[Library] CSV import failed for", f.name, err);
        failed.push(f.name);
      }
      setProgress({ done: i + 1, total: files.length });
    }

    setBusy(false);
    setProgress(null);

    if (created.length > 0) {
      // Navigate only for a clean single-file import; otherwise just refresh.
      const navigate = single && failed.length === 0;
      onImported(created, { navigate });
    }
    if (failed.length > 0) {
      setError(
        new Error(t("csvImport.someFailed", { names: failed.join(", ") })),
      );
      // Keep the modal open so the user sees which files failed.
    } else {
      onClose();
    }
  }

  const previewRows = previewText
    .split("\n")
    .slice(0, 4)
    .map((l) => l.split(delimiter));

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("csvImport.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("csvImport.subtitle")}
      </p>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <div className="rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-700 dark:bg-neutral-900/40">
          <div className="flex items-start justify-between gap-3">
            <p className="flex-1 text-neutral-600 dark:text-neutral-400">
              {t("csvImport.sampleHint")}
            </p>
            <div ref={sampleMenuRef} className="relative shrink-0">
              <button
                type="button"
                onClick={() => setSampleOpen((v) => !v)}
                className="inline-flex items-center gap-1 rounded-md border border-neutral-300 bg-white px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("csvImport.downloadSample")}
                <span aria-hidden>▾</span>
              </button>
              {sampleOpen && (
                <div
                  className="absolute right-0 z-10 mt-1 w-56 overflow-hidden rounded-md border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
                  onMouseLeave={() => setSampleOpen(false)}
                >
                  {SAMPLES.map((s) => (
                    <a
                      key={s.file}
                      href={`/samples/${s.file}`}
                      download
                      onClick={() => setSampleOpen(false)}
                      className="block px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      {t(s.labelKey)}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("csvImport.csvFiles")}
          <input
            type="file"
            accept=".csv,text/csv"
            multiple
            onChange={onPick}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutral-900 file:px-3 file:py-2 file:text-xs file:font-medium file:text-white hover:file:bg-neutral-800 dark:file:bg-neutral-100 dark:file:text-neutral-900"
          />
          <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
            {t("csvImport.multiHint")}
          </span>
        </label>

        {/* Single file → editable table name. Multiple → one table per file,
            named after the file (shown as a list). */}
        {single && (
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("csvImport.tableName")}
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("csvImport.tableNamePlaceholder")}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
        )}

        {files.length > 1 && (
          <div className="text-sm">
            <p className="mb-1 font-medium text-neutral-700 dark:text-neutral-300">
              {t("csvImport.willCreate", { count: files.length })}
            </p>
            <ul className="max-h-32 space-y-1 overflow-auto rounded-md border border-neutral-200 p-2 text-xs dark:border-neutral-800">
              {files.map((f, i) => (
                <li key={i} className="flex items-center justify-between gap-3">
                  <span className="truncate text-neutral-500 dark:text-neutral-400">
                    {f.name}
                  </span>
                  <span className="shrink-0 font-mono text-neutral-700 dark:text-neutral-300">
                    {tableNameForFile(f)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("csvImport.delimiter")}
            <select
              value={delimiter}
              onChange={(e) => setDelimiter(e.target.value)}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value=",">{t("csvImport.delimiterComma")}</option>
              <option value=";">{t("csvImport.delimiterSemicolon")}</option>
              <option value="\t">{t("csvImport.delimiterTab")}</option>
              <option value="|">{t("csvImport.delimiterPipe")}</option>
            </select>
          </label>
          <label className="flex items-end gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
            <input
              type="checkbox"
              checked={hasHeader}
              onChange={(e) => setHasHeader(e.target.checked)}
              className="mb-2 h-4 w-4"
            />
            <span className="mb-2">{t("csvImport.firstRowHeader")}</span>
          </label>
        </div>

        {previewText && (
          <div>
            <p className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("csvImport.previewLabel")}
              {files.length > 1 && ` · ${files[0].name}`}
            </p>
            <div className="mt-1 max-h-40 overflow-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-xs">
                <tbody>
                  {previewRows.map((row, i) => (
                    <tr
                      key={i}
                      className={
                        i === 0 && hasHeader
                          ? "bg-neutral-100 font-medium dark:bg-neutral-800"
                          : ""
                      }
                    >
                      {row.map((cell, j) => (
                        <td
                          key={j}
                          className="border-r border-neutral-200 px-2 py-1 dark:border-neutral-800"
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {error != null && <ErrorPanel title={t("common.importFailed")} error={error} />}

        <div className="flex items-center justify-end gap-3 border-t border-neutral-200 pt-4 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={busy || files.length === 0 || (single && !name.trim())}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {busy
              ? progress
                ? t("csvImport.importingProgress", {
                    done: progress.done,
                    total: progress.total,
                  })
                : t("common.importing")
              : files.length > 1
                ? t("csvImport.importN", { count: files.length })
                : t("common.import")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
