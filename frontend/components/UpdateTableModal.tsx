"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import {
  updateTableCells,
  updateTableCellsCsv,
  type TableUpdateResult,
} from "@/lib/library";
import { detectDelimiter, isBlankRow, parseDelimited } from "@/lib/parseDelimited";
import type { BulkColumn } from "@/lib/types";

// A file upload streams to the server (parsed there) — same 200 MB ceiling as
// the create-CSV import. Pasted data is sent as JSON, so it keeps a tighter
// cap. Only a slice of a file is read in the browser, just for the mapping UI.
const MAX_FILE_BYTES = 100 * 1024 * 1024;
const MAX_PASTE_CHARS = 20 * 1024 * 1024;
const MAX_ROWS = 200_000; // paste-only (mirrors the backend JSON row cap)
const HEADER_SLICE_BYTES = 1024 * 1024;

interface Props {
  tableId: number;
  columns: BulkColumn[];
  onClose: () => void;
  /** Called after a successful update so the grid behind the modal reloads. */
  onUpdated: () => void;
}

export function UpdateTableModal({ tableId, columns, onClose, onUpdated }: Props) {
  const { t } = useT();
  const [source, setSource] = useState<"file" | "paste">("file");
  const [delimiter, setDelimiter] = useState(","); // file mode only
  const [hasHeader, setHasHeader] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  // For a file we only read a leading slice — enough for the header + a few
  // preview rows. The full file is streamed to the server on submit.
  const [fileText, setFileText] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [filename, setFilename] = useState<string | null>(null);

  // source column index -> target table column id (null = don't import)
  const [mapping, setMapping] = useState<Record<number, number | null>>({});
  const [matchMode, setMatchMode] = useState<"key" | "order">("key");
  const [sourceKeyIndex, setSourceKeyIndex] = useState<number | null>(null);
  const [keyColumnId, setKeyColumnId] = useState<number | null>(null);
  const [skipEmpty, setSkipEmpty] = useState(true);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<TableUpdateResult | null>(null);

  const text = source === "file" ? fileText : pasteText;
  const effectiveDelimiter =
    source === "paste" ? detectDelimiter(pasteText) : delimiter;

  const parsed = useMemo(() => {
    if (!text.trim()) return { headers: [] as string[], rows: [] as string[][] };
    const all = parseDelimited(text, effectiveDelimiter).filter(
      (r) => !isBlankRow(r),
    );
    if (all.length === 0) return { headers: [] as string[], rows: [] as string[][] };
    const width = Math.max(...all.map((r) => r.length));
    const pad = (r: string[]) => {
      const c = r.slice();
      while (c.length < width) c.push("");
      return c;
    };
    if (hasHeader) {
      return {
        headers: pad(all[0]).map((h, i) => h.trim() || `Column ${i + 1}`),
        rows: all.slice(1).map(pad),
      };
    }
    return {
      headers: Array.from({ length: width }, (_, i) => `Column ${i + 1}`),
      rows: all.map(pad),
    };
  }, [text, effectiveDelimiter, hasHeader]);

  // Re-derive the default mapping + key whenever the detected columns change.
  const headerKey = parsed.headers.join("");
  useEffect(() => {
    const byName = new Map(
      columns.map((c) => [c.name.trim().toLowerCase(), c.id]),
    );
    const m: Record<number, number | null> = {};
    parsed.headers.forEach((h, i) => {
      m[i] = byName.get(h.trim().toLowerCase()) ?? null;
    });
    setMapping(m);
    const firstMapped = parsed.headers.findIndex((_, i) => m[i] != null);
    setSourceKeyIndex(
      firstMapped >= 0 ? firstMapped : parsed.headers.length ? 0 : null,
    );
    setKeyColumnId(
      firstMapped >= 0 ? m[firstMapped] : columns[0]?.id ?? null,
    );
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headerKey]);

  async function onPickFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    if (f.size > MAX_FILE_BYTES) {
      setError(new Error(t("updateTable.tooLarge")));
      return;
    }
    setFile(f);
    setFilename(f.name);
    setFileText(await f.slice(0, HEADER_SLICE_BYTES).text());
  }

  const mappings = useMemo(
    () =>
      parsed.headers
        .map((_, i) => ({ source_index: i, column_id: mapping[i] ?? null }))
        .filter(
          (m): m is { source_index: number; column_id: number } =>
            m.column_id != null,
        ),
    [parsed.headers, mapping],
  );

  const isFile = source === "file";
  // The paste path sends rows as JSON, so it carries the row cap; a file path
  // streams to the server (no client row limit, only the 200 MB byte cap).
  const tooManyRows = !isFile && parsed.rows.length > MAX_ROWS;
  const tooLongPaste = !isFile && pasteText.length > MAX_PASTE_CHARS;
  const keyReady =
    matchMode === "order" || (sourceKeyIndex != null && keyColumnId != null);
  // For a file we only sliced the head, so we gate on detected columns rather
  // than the (partial) preview row count.
  const haveData = isFile
    ? !!file && parsed.headers.length > 0
    : parsed.rows.length > 0;
  const canSubmit =
    !busy &&
    haveData &&
    !tooManyRows &&
    !tooLongPaste &&
    mappings.length > 0 &&
    keyReady;

  async function onSubmit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const res =
        isFile && file
          ? await updateTableCellsCsv(tableId, {
              file,
              delimiter,
              has_header: hasHeader,
              mappings,
              match_mode: matchMode,
              source_key_index: matchMode === "key" ? sourceKeyIndex : null,
              key_column_id: matchMode === "key" ? keyColumnId : null,
              skip_empty: skipEmpty,
            })
          : await updateTableCells(tableId, {
              rows: parsed.rows,
              mappings,
              match_mode: matchMode,
              source_key_index: matchMode === "key" ? sourceKeyIndex : null,
              key_column_id: matchMode === "key" ? keyColumnId : null,
              skip_empty: skipEmpty,
            });
      setResult(res);
      onUpdated();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-3xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("updateTable.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("updateTable.subtitle")}
      </p>

      {result ? (
        <div className="mt-5 space-y-4">
          <div className="rounded-md border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950/40 dark:text-green-300">
            <p className="font-medium">{t("updateTable.doneTitle")}</p>
            <ul className="mt-1 list-inside list-disc text-xs">
              <li>
                {t("updateTable.doneCells", {
                  cells: result.updated_cells,
                  rows: result.affected_table_rows,
                })}
              </li>
              <li>{t("updateTable.doneMatched", { n: result.matched_rows })}</li>
              {result.unmatched_rows > 0 && (
                <li className="text-amber-700 dark:text-amber-300">
                  {t("updateTable.doneUnmatched", { n: result.unmatched_rows })}
                </li>
              )}
            </ul>
          </div>
          <div className="flex justify-end border-t border-neutral-200 pt-4 dark:border-neutral-800">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {t("common.done")}
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {/* source: file vs paste */}
          <div className="inline-flex rounded-md border border-neutral-300 p-0.5 text-xs dark:border-neutral-700">
            {(["file", "paste"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSource(s)}
                className={
                  "rounded px-3 py-1 font-medium " +
                  (source === s
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "text-neutral-600 dark:text-neutral-300")
                }
              >
                {s === "file"
                  ? t("updateTable.sourceFile")
                  : t("updateTable.sourcePaste")}
              </button>
            ))}
          </div>

          {source === "file" ? (
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("updateTable.fileLabel")}
                <input
                  type="file"
                  accept=".csv,.tsv,text/csv,text/tab-separated-values,text/plain"
                  onChange={onPickFile}
                  className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutral-900 file:px-3 file:py-2 file:text-xs file:font-medium file:text-white hover:file:bg-neutral-800 dark:file:bg-neutral-100 dark:file:text-neutral-900"
                />
                {filename && (
                  <span className="mt-1 inline-block text-xs text-neutral-500 dark:text-neutral-400">
                    {filename}
                  </span>
                )}
              </label>
              <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("csvImport.delimiter")}
                <select
                  value={delimiter}
                  onChange={(e) => setDelimiter(e.target.value)}
                  className="mt-1 block rounded-md border border-neutral-300 px-2 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value=",">{t("csvImport.delimiterComma")}</option>
                  <option value=";">{t("csvImport.delimiterSemicolon")}</option>
                  <option value="\t">{t("csvImport.delimiterTab")}</option>
                  <option value="|">{t("csvImport.delimiterPipe")}</option>
                </select>
              </label>
            </div>
          ) : (
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("updateTable.pasteLabel")}
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                rows={6}
                placeholder={t("updateTable.pastePlaceholder")}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 font-mono text-xs dark:border-neutral-700 dark:bg-neutral-900"
              />
            </label>
          )}

          <label className="flex items-center gap-2 text-xs font-medium text-neutral-700 dark:text-neutral-300">
            <input
              type="checkbox"
              checked={hasHeader}
              onChange={(e) => setHasHeader(e.target.checked)}
              className="h-4 w-4"
            />
            {t("updateTable.firstRowHeader")}
          </label>

          {parsed.headers.length > 0 && (
            <>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                {isFile
                  ? t("updateTable.detectedFile", {
                      cols: parsed.headers.length,
                    })
                  : t("updateTable.detected", {
                      cols: parsed.headers.length,
                      rows: parsed.rows.length,
                    })}
              </p>

              {/* column mapping */}
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {t("updateTable.mapHeading")}
                </p>
                <div className="overflow-hidden rounded-md border border-neutral-200 dark:border-neutral-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-neutral-50 text-[11px] uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                      <tr>
                        <th className="px-3 py-1.5 font-medium">
                          {t("updateTable.mapFrom")}
                        </th>
                        <th className="px-3 py-1.5 font-medium">
                          {t("updateTable.mapSample")}
                        </th>
                        <th className="px-3 py-1.5 font-medium">
                          {t("updateTable.mapTo")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                      {parsed.headers.map((h, i) => (
                        <tr key={i}>
                          <td className="px-3 py-1.5 font-mono text-neutral-700 dark:text-neutral-300">
                            {h}
                          </td>
                          <td className="max-w-[12rem] truncate px-3 py-1.5 text-neutral-500 dark:text-neutral-400">
                            {parsed.rows[0]?.[i] ?? ""}
                          </td>
                          <td className="px-3 py-1.5">
                            <select
                              value={mapping[i] ?? ""}
                              onChange={(e) =>
                                setMapping((cur) => ({
                                  ...cur,
                                  [i]: e.target.value
                                    ? Number(e.target.value)
                                    : null,
                                }))
                              }
                              className="w-full rounded border border-neutral-300 px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900"
                            >
                              <option value="">
                                {t("updateTable.dontImport")}
                              </option>
                              {columns.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name}
                                </option>
                              ))}
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* matching mode */}
              <div className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {t("updateTable.matchHeading")}
                </p>
                <div className="space-y-2 text-sm">
                  <label className="flex items-start gap-2">
                    <input
                      type="radio"
                      checked={matchMode === "key"}
                      onChange={() => setMatchMode("key")}
                      className="mt-1"
                    />
                    <span>
                      <span className="font-medium text-neutral-800 dark:text-neutral-200">
                        {t("updateTable.matchKey")}
                      </span>
                      {matchMode === "key" && (
                        <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="text-neutral-500 dark:text-neutral-400">
                            {t("updateTable.matchKeyUsing")}
                          </span>
                          <select
                            value={sourceKeyIndex ?? ""}
                            onChange={(e) =>
                              setSourceKeyIndex(
                                e.target.value ? Number(e.target.value) : null,
                              )
                            }
                            className="rounded border border-neutral-300 px-1.5 py-1 dark:border-neutral-700 dark:bg-neutral-900"
                          >
                            {parsed.headers.map((h, i) => (
                              <option key={i} value={i}>
                                {h}
                              </option>
                            ))}
                          </select>
                          <span className="text-neutral-500 dark:text-neutral-400">
                            {t("updateTable.matchKeyMatches")}
                          </span>
                          <select
                            value={keyColumnId ?? ""}
                            onChange={(e) =>
                              setKeyColumnId(
                                e.target.value ? Number(e.target.value) : null,
                              )
                            }
                            className="rounded border border-neutral-300 px-1.5 py-1 dark:border-neutral-700 dark:bg-neutral-900"
                          >
                            {columns.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                        </span>
                      )}
                    </span>
                  </label>
                  <label className="flex items-start gap-2">
                    <input
                      type="radio"
                      checked={matchMode === "order"}
                      onChange={() => setMatchMode("order")}
                      className="mt-1"
                    />
                    <span>
                      <span className="font-medium text-neutral-800 dark:text-neutral-200">
                        {t("updateTable.matchOrder")}
                      </span>
                      <span className="block text-xs text-neutral-500 dark:text-neutral-400">
                        {t("updateTable.matchOrderHint")}
                      </span>
                    </span>
                  </label>
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-neutral-700 dark:text-neutral-300">
                <input
                  type="checkbox"
                  checked={skipEmpty}
                  onChange={(e) => setSkipEmpty(e.target.checked)}
                  className="h-4 w-4"
                />
                {t("updateTable.skipEmpty")}
              </label>
            </>
          )}

          {tooManyRows && (
            <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              {t("updateTable.tooManyRows", { max: MAX_ROWS })}
            </p>
          )}
          {tooLongPaste && (
            <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              {t("updateTable.pasteTooLong")}
            </p>
          )}
          {error != null && (
            <ErrorPanel title={t("updateTable.failed")} error={error} />
          )}

          <div className="flex items-center justify-end gap-3 border-t border-neutral-200 pt-4 dark:border-neutral-800">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              disabled={!canSubmit}
              onClick={onSubmit}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {busy
                ? t("updateTable.updating")
                : t("updateTable.updateBtn", { n: mappings.length })}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
