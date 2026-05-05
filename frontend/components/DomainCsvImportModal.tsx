"use client";

import { useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import { importDomainsCsv, type CsvImportResult } from "@/lib/domains";

const SAMPLE_CSV = `name,base_url,cms_type,auth_type,credentials,languages,multilingual_plugin
Site A,https://site-a.example.com,wordpress,wp_app_password,user:appPwd,en,none
Site B,https://site-b.example.com,wordpress,wp_app_password,user:appPwd,"en,de,fr",polylang
Site C,https://site-c.example.com,custom,bearer,abc123token,en,none`;

function downloadSampleCsv() {
  const blob = new Blob([SAMPLE_CSV], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "domains_sample.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function DomainCsvImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const { t } = useT();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CsvImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError(t("domainCsv.pickFirst"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await importDomainsCsv(file);
      setResult(r);
      if (r.inserted > 0) onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.importFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <form onSubmit={onSubmit} className="space-y-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("domainCsv.title")}
        </h2>

        <div className="text-xs text-neutral-600 dark:text-neutral-400">
          <p className="mb-1">{t("domainCsv.requiredColumns")}</p>
          <code className="font-mono">
            name, base_url, cms_type, auth_type, credentials, languages, multilingual_plugin
          </code>
        </div>

        <details className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-950">
          <summary className="cursor-pointer font-medium text-neutral-700 dark:text-neutral-300">
            {t("domainCsv.sample")}
          </summary>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-neutral-500 dark:text-neutral-400">
              {t("domainCsv.sampleStart")}
            </span>
            <button
              type="button"
              onClick={downloadSampleCsv}
              className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("domainCsv.downloadSample")}
            </button>
          </div>
          <pre className="mt-2 whitespace-pre-wrap font-mono text-neutral-700 dark:text-neutral-300">
{SAMPLE_CSV}
          </pre>
        </details>

        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="block w-full text-sm text-neutral-700 dark:text-neutral-300"
        />

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
            <p className="font-medium">
              {t("domainCsv.summary", { inserted: result.inserted, skipped: result.skipped })}
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-xs">
                {result.errors.map((er) => (
                  <li key={er.row}>
                    {t("domainCsv.rowError", { row: er.row, detail: er.detail })}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.close")}
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("common.importing") : t("common.import")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
