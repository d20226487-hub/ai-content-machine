"use client";

import { useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import { importDomainsCsv, type CsvImportResult } from "@/lib/domains";

// One ready-made template per CMS type. Each file shows both shapes —
// single-language rows (multilingual_plugin=none) and multilingual ones
// (polylang/wpml for WordPress, several languages for Custom CMS) — so the
// single/multi split isn't worth a separate file. Custom-CMS carries the
// extra custom_config columns.
const SAMPLES: {
  file: string;
  labelKey: "domainCsv.sampleWp" | "domainCsv.sampleCustom";
}[] = [
  { file: "wordpress.csv", labelKey: "domainCsv.sampleWp" },
  { file: "custom-cms.csv", labelKey: "domainCsv.sampleCustom" },
];

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
  const [sampleOpen, setSampleOpen] = useState(false);

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
          <code className="block font-mono">
            name, base_url, cms_type, auth_type, credentials, languages, multilingual_plugin
          </code>
          <p className="mt-1.5 mb-1">{t("domainCsv.customColumns")}</p>
          <code className="block font-mono">
            endpoint_path, body_template, response_id_path, response_url_path
          </code>
        </div>

        <div className="rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-700 dark:bg-neutral-900/40">
          <div className="flex items-start justify-between gap-3">
            <p className="flex-1 text-neutral-600 dark:text-neutral-400">
              {t("domainCsv.sampleHint")}
            </p>
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={() => setSampleOpen((v) => !v)}
                className="inline-flex items-center gap-1 rounded-md border border-neutral-300 bg-white px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("domainCsv.downloadSample")}
                <span aria-hidden>▾</span>
              </button>
              {sampleOpen && (
                <div
                  className="absolute right-0 z-10 mt-1 w-60 overflow-hidden rounded-md border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
                  onMouseLeave={() => setSampleOpen(false)}
                >
                  {SAMPLES.map((s) => (
                    <a
                      key={s.file}
                      href={`/samples/domains/${s.file}`}
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
