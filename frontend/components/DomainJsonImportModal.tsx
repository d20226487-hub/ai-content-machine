"use client";

import { useMemo, useRef, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import {
  importDomainsJson,
  type CsvImportResult,
  type DomainCreatePayload,
} from "@/lib/domains";

/**
 * Sample payload — two WP sites with the same profiles, plus one Custom CMS
 * site. Pasted into the textarea as a starter; users typically tweak from
 * here for their fleet.
 */
const SAMPLE_JSON = [
  {
    name: "Site A",
    base_url: "https://site-a.example.com",
    cms_type: "wordpress",
    auth_type: "wp_app_password",
    credentials: "user:application_password",
    languages: ["en"],
    multilingual_plugin: "none",
    publish_config: {
      profiles: [
        {
          name: "Article",
          post_type: "posts",
          fields: [
            { key: "title", label: "Title", type: "text", required: true },
            { key: "content", label: "Content", type: "textarea", required: true },
            { key: "slug", label: "Slug", type: "text" },
            { key: "status", label: "Status", type: "select", options: ["publish", "draft"], required: true },
          ],
        },
        {
          name: "Page",
          post_type: "pages",
          fields: [
            { key: "title", label: "Title", type: "text", required: true },
            { key: "content", label: "Content", type: "textarea", required: true },
          ],
        },
      ],
    },
  },
  {
    name: "Site B",
    base_url: "https://site-b.example.com",
    cms_type: "wordpress",
    auth_type: "wp_app_password",
    credentials: "user:application_password",
    languages: ["en", "ru"],
    multilingual_plugin: "polylang",
    publish_config: {
      profiles: [
        {
          name: "Article",
          post_type: "posts",
          fields: [
            { key: "title", label: "Title", type: "text", required: true },
            { key: "content", label: "Content", type: "textarea", required: true },
          ],
        },
      ],
    },
  },
  {
    name: "Custom Site",
    base_url: "https://api.example.com",
    cms_type: "custom",
    auth_type: "bearer",
    credentials: "your-bearer-token",
    languages: ["en"],
    custom_config: {
      endpoint_path: "/posts",
      body_template: { title: "{{title}}", body: "{{content}}" },
      response_id_path: "id",
      response_url_path: "url",
    },
  },
];

const SAMPLE_TEXT = JSON.stringify(SAMPLE_JSON, null, 2);

function downloadSampleJson() {
  const blob = new Blob([SAMPLE_TEXT], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "domains_sample.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function DomainJsonImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const { t } = useT();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CsvImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Client-side parse preview so a typo doesn't waste a network round-trip.
  const parsePreview = useMemo<
    { ok: true; count: number } | { ok: false; detail: string } | null
  >(() => {
    if (!text.trim()) return null;
    try {
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) {
        return { ok: false, detail: t("domainJson.errNotArray") };
      }
      return { ok: true, count: parsed.length };
    } catch (e) {
      return {
        ok: false,
        detail: e instanceof Error ? e.message : String(e),
      };
    }
  }, [text, t]);

  async function onPickFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const content = await file.text();
    setText(content);
    // Clear the input so picking the same file twice re-fires onChange.
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    let parsed: DomainCreatePayload[];
    try {
      const raw = JSON.parse(text);
      if (!Array.isArray(raw)) {
        setError(t("domainJson.errNotArray"));
        return;
      }
      parsed = raw as DomainCreatePayload[];
    } catch (e) {
      setError(e instanceof Error ? e.message : t("domainJson.errParse"));
      return;
    }
    if (parsed.length === 0) {
      setError(t("domainJson.errEmpty"));
      return;
    }
    setBusy(true);
    try {
      const r = await importDomainsJson(parsed);
      setResult(r);
      if (r.inserted > 0) onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.importFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-3xl">
      <form onSubmit={onSubmit} className="space-y-4">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("domainJson.title")}
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("domainJson.subtitle")}
        </p>

        <details className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-800 dark:bg-neutral-950">
          <summary className="cursor-pointer font-medium text-neutral-700 dark:text-neutral-300">
            {t("domainJson.sample")}
          </summary>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-neutral-500 dark:text-neutral-400">
              {t("domainJson.sampleStart")}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setText(SAMPLE_TEXT)}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("domainJson.loadSample")}
              </button>
              <button
                type="button"
                onClick={downloadSampleJson}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("domainJson.downloadSample")}
              </button>
            </div>
          </div>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-neutral-700 dark:text-neutral-300">
{SAMPLE_TEXT}
          </pre>
        </details>

        <div className="space-y-1">
          <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("domainJson.uploadLabel")}
          </label>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            onChange={onPickFile}
            className="block w-full text-sm text-neutral-700 dark:text-neutral-300"
          />
        </div>

        <div className="space-y-1">
          <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("domainJson.pasteLabel")}
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={14}
            spellCheck={false}
            placeholder='[{"name":"…","base_url":"…",…}]'
            className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-xs text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          {parsePreview && (
            <p
              className={
                "text-[11px] " +
                (parsePreview.ok
                  ? "text-green-700 dark:text-green-400"
                  : "text-amber-700 dark:text-amber-400")
              }
            >
              {parsePreview.ok
                ? t("domainJson.parseOk", { count: parsePreview.count })
                : t("domainJson.parseErr", { detail: parsePreview.detail })}
            </p>
          )}
        </div>

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        {result && (
          <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
            <p className="font-medium">
              {t("domainJson.summary", {
                inserted: result.inserted,
                skipped: result.skipped,
              })}
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-xs">
                {result.errors.map((er) => (
                  <li key={er.row}>
                    {t("domainJson.rowError", { row: er.row, detail: er.detail })}
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
            disabled={busy || !parsePreview?.ok}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("common.importing") : t("common.import")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
