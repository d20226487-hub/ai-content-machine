"use client";

import { ChangeEvent, useState } from "react";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { resolveDomainNames } from "@/lib/publishLanguages";

import { parseCsv, parseLanguagesCell } from "./csvParse";

/**
 * Imported row, post-parse + post-validation. Carries the resolved
 * domain id so the parent can populate `picked` chips directly without
 * a second round-trip. Languages come back already normalized (lower-
 * cased, deduped, sorted).
 */
export interface ImportedRow {
  domain_id: number;
  domain_name: string;
  has_credentials: boolean;
  languages: string[];
}

/**
 * CSV import flow for "different languages per site" — populates the
 * standalone sync form with N chips + per-site language sets.
 *
 * CSV shape: ``domain,languages`` where the languages cell is a
 * comma/space/semicolon-separated list (so an Excel cell like
 * ``"ru, en, de"`` works as-is). Header row is optional — we detect it
 * by checking whether the first cell of row 0 equals ``domain`` case-
 * insensitively.
 *
 * Validation: we hit `POST /publish/languages/resolve` with the parsed
 * domain names. If ANY name is unknown we hard-fail the import (per
 * the user's preference) so a typoed row can't silently skip.
 *
 * The parent receives the validated rows via ``onImported`` and decides
 * what to do with them (typically: replace its chip list + per-site
 * language map and flip on per-site mode).
 */
export function LanguageCsvImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (rows: ImportedRow[]) => void;
}) {
  const { t } = useT();
  const [filename, setFilename] = useState<string | null>(null);
  const [parsedRows, setParsedRows] = useState<ImportedRow[] | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [unknownNames, setUnknownNames] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function onPick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    setParseError(null);
    setParsedRows(null);
    setUnknownNames([]);

    let text: string;
    try {
      text = await file.text();
    } catch (err) {
      setParseError(t("langCsv.errorRead", { err: String(err) }));
      return;
    }

    const rows = parseCsv(text);
    if (rows.length === 0) {
      setParseError(t("langCsv.errorEmpty"));
      return;
    }

    // Header detection: tolerate either "domain,languages" or any case
    // variant. If row 0 doesn't look like a header, treat it as data.
    const hasHeader =
      rows[0].length >= 2 && rows[0][0].trim().toLowerCase() === "domain";
    const dataRows = hasHeader ? rows.slice(1) : rows;

    // First pass: parse the CSV into name + languages pairs. The full
    // ImportedRow shape (with id + has_credentials) is built later, after
    // the resolve call confirms each name exists.
    type ParsedRow = { domain_name: string; languages: string[] };
    const parsed: ParsedRow[] = [];
    const errors: string[] = [];
    dataRows.forEach((row, idx) => {
      const lineNo = idx + (hasHeader ? 2 : 1);
      if (row.length < 2) {
        errors.push(
          t("langCsv.errorRowShape", { line: lineNo, cols: row.length }),
        );
        return;
      }
      const domain = row[0].trim();
      if (!domain) {
        errors.push(t("langCsv.errorRowEmptyDomain", { line: lineNo }));
        return;
      }
      const langs = parseLanguagesCell(row[1]);
      if (langs.length === 0) {
        errors.push(t("langCsv.errorRowEmptyLangs", { line: lineNo, domain }));
        return;
      }
      parsed.push({ domain_name: domain, languages: langs });
    });

    if (errors.length > 0) {
      setParseError(errors.slice(0, 5).join("\n"));
      return;
    }
    if (parsed.length === 0) {
      setParseError(t("langCsv.errorNoRows"));
      return;
    }

    // Dedup by domain name — last row wins.
    const byNameParsed = new Map<string, ParsedRow>();
    for (const r of parsed) byNameParsed.set(r.domain_name, r);
    const deduped = Array.from(byNameParsed.values());

    setBusy(true);
    try {
      const resolved = await resolveDomainNames(
        deduped.map((r) => r.domain_name),
      );
      if (resolved.unknown.length > 0) {
        setUnknownNames(resolved.unknown);
        setParsedRows([]); // suppress preview; user must fix CSV first
        return;
      }
      // Join the parsed languages with the resolved domain rows by name.
      // Both sides are already deduped + ordered so this is O(N).
      const byName = new Map(resolved.known.map((k) => [k.name, k]));
      const enriched: ImportedRow[] = deduped.map((r) => {
        const k = byName.get(r.domain_name)!;
        return {
          domain_id: k.id,
          domain_name: k.name,
          has_credentials: k.has_credentials,
          languages: r.languages,
        };
      });
      setParsedRows(enriched);
    } catch (err) {
      setParseError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const canApply =
    parsedRows != null && parsedRows.length > 0 && unknownNames.length === 0;

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("langCsv.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("langCsv.subtitle")}
      </p>

      <div className="mt-4 rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-700 dark:bg-neutral-900/40">
        <p className="text-neutral-600 dark:text-neutral-400">
          {t("langCsv.hint")}
        </p>
        <a
          href="/samples/language-sync-multi-site.csv"
          download
          className="mt-1 inline-block font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          {t("langCsv.downloadSample")}
        </a>
      </div>

      <label className="mt-4 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("langCsv.fileLabel")}
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

      {busy && (
        <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
          {t("langCsv.validating")}
        </p>
      )}

      {parseError && (
        <pre className="mt-3 whitespace-pre-wrap rounded bg-red-50 px-2 py-1 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {parseError}
        </pre>
      )}

      {unknownNames.length > 0 && (
        <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs dark:bg-red-950/40">
          <p className="font-medium text-red-800 dark:text-red-300">
            {t("langCsv.errorUnknown", { count: unknownNames.length })}
          </p>
          <ul className="mt-1 max-h-32 space-y-0.5 overflow-auto pl-4 font-mono text-[11px] text-red-700 dark:text-red-300">
            {unknownNames.slice(0, 12).map((n) => (
              <li key={n}>• {n}</li>
            ))}
            {unknownNames.length > 12 && (
              <li>…{t("bulkPub.andMore", { count: unknownNames.length - 12 })}</li>
            )}
          </ul>
          <p className="mt-2 text-[11px] text-red-700 dark:text-red-300">
            {t("langCsv.errorUnknownFix")}
          </p>
        </div>
      )}

      {parsedRows && unknownNames.length === 0 && (
        <div className="mt-3 rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs dark:border-neutral-800 dark:bg-neutral-950/40">
          <p className="font-medium text-neutral-900 dark:text-neutral-100">
            {t("langCsv.previewTitle", { count: parsedRows.length })}
          </p>
          <ul className="mt-2 max-h-40 space-y-0.5 overflow-auto font-mono text-[11px] text-neutral-700 dark:text-neutral-300">
            {parsedRows.slice(0, 12).map((r) => (
              <li key={r.domain_name} className="flex justify-between gap-2">
                <span className="truncate">{r.domain_name}</span>
                <span className="shrink-0 text-neutral-500 dark:text-neutral-400">
                  {r.languages.join(", ")}
                </span>
              </li>
            ))}
            {parsedRows.length > 12 && (
              <li className="text-neutral-500 dark:text-neutral-400">
                …{t("bulkPub.andMore", { count: parsedRows.length - 12 })}
              </li>
            )}
          </ul>
        </div>
      )}

      <div className="mt-4 flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("common.cancel")}
        </button>
        <button
          type="button"
          disabled={!canApply}
          onClick={() => {
            if (parsedRows) onImported(parsedRows);
          }}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60 dark:bg-blue-500"
        >
          {t("langCsv.applyButton")}
        </button>
      </div>
    </Modal>
  );
}
