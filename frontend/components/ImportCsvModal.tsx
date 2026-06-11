"use client";

import { ChangeEvent, FormEvent, useRef, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import { importCsv } from "@/lib/library";
import type { BulkTable } from "@/lib/types";

interface Props {
  onClose: () => void;
  onImported: (table: BulkTable) => void;
}

const SAMPLES: { file: string; labelKey: "csvImport.sampleWpSingle" | "csvImport.sampleWpMulti" | "csvImport.sampleCustomSingle" | "csvImport.sampleCustomMulti" }[] = [
  { file: "wordpress-single-site.csv", labelKey: "csvImport.sampleWpSingle" },
  { file: "wordpress-multi-site.csv", labelKey: "csvImport.sampleWpMulti" },
  { file: "custom-cms-single-site.csv", labelKey: "csvImport.sampleCustomSingle" },
  { file: "custom-cms-multi-site.csv", labelKey: "csvImport.sampleCustomMulti" },
];

export function ImportCsvModal({ onClose, onImported }: Props) {
  const { t } = useT();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  // Only the first slice is read for the preview; the full file is streamed to
  // the server as multipart on submit (never loaded into a JS string).
  const [previewText, setPreviewText] = useState("");
  const [delimiter, setDelimiter] = useState(",");
  const [hasHeader, setHasHeader] = useState(true);
  const [filename, setFilename] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [sampleOpen, setSampleOpen] = useState(false);
  const sampleMenuRef = useRef<HTMLDivElement | null>(null);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setPreviewText(await f.slice(0, 64 * 1024).text());
    setFilename(f.name);
    if (!name.trim()) {
      setName(f.name.replace(/\.[^.]+$/, ""));
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const table = await importCsv({
        name: name.trim(),
        file,
        delimiter,
        has_header: hasHeader,
      });
      onImported(table);
      onClose();
    } catch (err) {
      console.error("[Library] CSV import failed", err);
      setError(err);
    } finally {
      setBusy(false);
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
          {t("csvImport.csvFile")}
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={onPick}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutral-900 file:px-3 file:py-2 file:text-xs file:font-medium file:text-white hover:file:bg-neutral-800 dark:file:bg-neutral-100 dark:file:text-neutral-900"
          />
          {filename && (
            <span className="mt-1 inline-block text-xs text-neutral-500 dark:text-neutral-400">
              {filename}
            </span>
          )}
        </label>

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
            disabled={busy || !name.trim() || !file}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {busy ? t("common.importing") : t("common.import")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
