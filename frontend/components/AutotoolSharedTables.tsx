"use client";

import { useCallback, useEffect, useState } from "react";

import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { ApiError } from "@/lib/api";
import {
  getPostPreview,
  listSharedTables,
  type AutotoolPostPreview,
  type AutotoolTableItem,
  type AutotoolTablesPage,
} from "@/lib/autotool";
import { useT } from "@/lib/i18n-context";

const PAGE_SIZE = 20;

/**
 * "Shared tables" section on /publish/autotool: every table currently exposed
 * to Autotool, paginated, each with a "View POST request" button that shows the
 * exact ImportPosts POST that would be sent (with a remappable site column).
 */
export function AutotoolSharedTables() {
  const { t } = useT();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AutotoolTablesPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<AutotoolTableItem | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    listSharedTables(page, PAGE_SIZE)
      .then(setData)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      )
      .finally(() => setLoading(false));
  }, [page, t]);

  useEffect(() => load(), [load]);

  return (
    <section className="max-w-3xl">
      <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
        {t("autotoolCfg.sharedHeading")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("autotoolCfg.sharedSubtitle")}
      </p>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {loading && !data ? (
        <p className="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      ) : data && data.items.length === 0 ? (
        <p className="mt-3 rounded-lg border border-dashed border-neutral-300 px-4 py-6 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
          {t("autotoolCfg.sharedEmpty")}
        </p>
      ) : data ? (
        <>
          <ul className="mt-3 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {data.items.map((it) => (
              <li
                key={it.id}
                className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium text-neutral-900 dark:text-neutral-100">
                    {it.name}
                  </span>
                  <span className="text-xs text-neutral-500 dark:text-neutral-400">
                    {t("autotoolCfg.rowsCols", {
                      rows: it.row_count,
                      cols: it.column_count,
                    })}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => setPreview(it)}
                  className="shrink-0 rounded-md border border-neutral-300 px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("autotoolCfg.viewRequest")}
                </button>
              </li>
            ))}
          </ul>
          <Pagination
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={setPage}
          />
        </>
      ) : null}

      {preview && (
        <PostRequestModal table={preview} onClose={() => setPreview(null)} />
      )}
    </section>
  );
}

function PostRequestModal({
  table,
  onClose,
}: {
  table: AutotoolTableItem;
  onClose: () => void;
}) {
  const { t } = useT();
  const [siteColumnId, setSiteColumnId] = useState<number | null>(null);
  const [touchedColumn, setTouchedColumn] = useState(false);
  const [data, setData] = useState<AutotoolPostPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getPostPreview(table.id, touchedColumn ? siteColumnId : undefined)
      .then((p) => {
        if (cancelled) return;
        setData(p);
        if (!touchedColumn) setSiteColumnId(p.site_column_id);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : t("common.failedToLoad")),
      );
    return () => {
      cancelled = true;
    };
  }, [table.id, siteColumnId, touchedColumn, t]);

  const requestText = data
    ? `${data.method} ${data.url ?? "—"}\n\n` +
      Object.entries(data.headers)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n") +
      `\n\n` +
      JSON.stringify(data.body, null, 2)
    : "";

  async function copy() {
    try {
      await navigator.clipboard.writeText(requestText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("autotoolCfg.previewTitle", { name: table.name })}
      </h3>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {data && (
        <div className="mt-4 space-y-4">
          {!data.target_configured && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              {t("autotoolCfg.noTarget")}
            </p>
          )}
          {!data.api_key_configured && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              {t("autotoolCfg.noKey")}
            </p>
          )}

          {/* Site column remap */}
          <label className="block text-sm">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">
              {t("autotoolCfg.siteColumn")}
            </span>
            <span className="mt-1 flex items-center gap-2">
              <select
                value={siteColumnId ?? ""}
                onChange={(e) => {
                  setTouchedColumn(true);
                  setSiteColumnId(e.target.value ? Number(e.target.value) : null);
                }}
                className="rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">{t("autotoolCfg.siteColumnNone")}</option>
                {data.columns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.id === data.detected_site_column_id
                      ? ` (${t("autotoolCfg.detected")})`
                      : ""}
                  </option>
                ))}
              </select>
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("autotoolCfg.siteCount", { n: data.site_count })}
              </span>
            </span>
          </label>

          {/* Full request */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t("autotoolCfg.request")}
              </span>
              <button
                type="button"
                onClick={() => void copy()}
                className="text-xs font-medium text-neutral-600 hover:underline dark:text-neutral-300"
              >
                {copied ? t("autotool.copied") : t("autotoolCfg.copy")}
              </button>
            </div>
            <pre className="max-h-80 overflow-auto rounded-md bg-neutral-50 p-3 text-xs leading-relaxed text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
              {requestText}
            </pre>
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {t("autotoolCfg.keyMaskedNote")}
            </p>
          </div>
        </div>
      )}

      <div className="mt-5 flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("autotoolCfg.close")}
        </button>
      </div>
    </Modal>
  );
}
