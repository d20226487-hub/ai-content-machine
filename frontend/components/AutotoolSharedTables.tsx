"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Modal } from "@/components/Modal";
import { Pagination } from "@/components/Pagination";
import { ApiError } from "@/lib/api";
import {
  createAutotoolRun,
  getPostPreview,
  listSharedTables,
  type AutotoolPostPreview,
  type AutotoolTableItem,
  type AutotoolTablesPage,
} from "@/lib/autotool";
import { autotoolCsvUrl } from "@/lib/library";
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
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
          {t("autotoolCfg.sharedHeading")}
        </h2>
        <Link
          href="/publish/autotool/runs"
          className="shrink-0 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          {t("autotoolCfg.viewRuns")}
        </Link>
      </div>
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
  const router = useRouter();
  const [siteColumnId, setSiteColumnId] = useState<number | null>(null);
  const [touchedColumn, setTouchedColumn] = useState(false);
  const [pageSize, setPageSize] = useState(50);
  const [data, setData] = useState<AutotoolPostPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [copiedFile, setCopiedFile] = useState<string | null>(null);
  // Operator has acknowledged the append-mode duplication risk (required before
  // sending a table whose included `mode` column holds "append").
  const [ackAppend, setAckAppend] = useState(false);

  const appendRows = data?.append_row_count ?? 0;
  const hasAppend = appendRows > 0;

  async function copyCsvLink(file: string) {
    try {
      await navigator.clipboard.writeText(autotoolCsvUrl(file));
      setCopiedFile(file);
      setTimeout(() => setCopiedFile(null), 1500);
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  useEffect(() => {
    let cancelled = false;
    getPostPreview(table.id, touchedColumn ? siteColumnId : undefined, pageSize)
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
  }, [table.id, siteColumnId, touchedColumn, pageSize, t]);

  function fmtRequest(body: object): string {
    if (!data) return "";
    return (
      `${data.method} ${data.url ?? "—"}\n` +
      Object.entries(data.headers)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n") +
      `\n\n` +
      JSON.stringify(body, null, 2)
    );
  }

  async function copyAll() {
    if (!data) return;
    const text = data.requests
      .map((r) => fmtRequest(r.body))
      .join("\n\n— — —\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  async function send() {
    if (!data) return;
    setSending(true);
    setSendError(null);
    try {
      const run = await createAutotoolRun(
        table.id,
        touchedColumn ? siteColumnId : undefined,
        pageSize,
        ackAppend,
      );
      // Hand off to the run's progress page.
      router.push(`/publish/autotool/runs/${run.id}`);
    } catch (e) {
      setSendError(
        e instanceof ApiError ? e.message : t("common.somethingWentWrong"),
      );
      setSending(false);
    }
  }

  const unmatched = data ? data.table_row_count - data.total_rows_matched : 0;

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
          {data.missing_required_columns.length > 0 && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {t("autotoolCfg.missingRequired", {
                cols: data.missing_required_columns.join(", "),
              })}
            </p>
          )}
          {hasAppend && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
              <p className="font-medium">{t("autotoolCfg.appendWarnTitle")}</p>
              <p className="mt-1">
                {t("autotoolCfg.appendWarn", { n: appendRows })}
              </p>
              {data.previously_sent && (
                <p className="mt-1 font-medium">
                  {t("autotoolCfg.appendWarnSent")}
                </p>
              )}
            </div>
          )}

          {/* Site column remap */}
          <label className="block text-sm">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">
              {t("autotoolCfg.siteColumn")}
            </span>
            <span className="mt-1 flex flex-wrap items-center gap-2">
              <select
                value={siteColumnId ?? ""}
                onChange={(e) => {
                  setTouchedColumn(true);
                  setSiteColumnId(e.target.value ? Number(e.target.value) : null);
                  // A column change regroups the requests; drop stale send state.
                  setConfirming(false);
                  setSendError(null);
                  setAckAppend(false);
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
                {t("autotoolCfg.splitSummary", {
                  domains: data.domain_count,
                  pages: data.page_count,
                  rows: data.total_rows_matched,
                })}
              </span>
            </span>
          </label>

          {/* Rows per request (page size) */}
          <label className="block text-sm">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">
              {t("autotoolCfg.pageSizeLabel")}
            </span>
            <span className="mt-1 flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={1}
                max={1000}
                value={pageSize}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10);
                  if (Number.isNaN(v)) return;
                  setPageSize(Math.max(1, Math.min(1000, v)));
                  // A new page size regroups the requests; drop stale send state.
                  setConfirming(false);
                  setSendError(null);
                  setAckAppend(false);
                }}
                className="w-24 rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("autotoolCfg.pageSizeHint")}
              </span>
            </span>
          </label>

          {unmatched > 0 && (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              {t("autotoolCfg.unmatchedWarn", { n: unmatched })}
            </p>
          )}

          {/* Per-domain requests */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t("autotoolCfg.requestsHeading", {
                  n: data.page_count,
                  size: data.page_size,
                })}
              </span>
              {data.requests.length > 0 && (
                <button
                  type="button"
                  onClick={() => void copyAll()}
                  className="text-xs font-medium text-neutral-600 hover:underline dark:text-neutral-300"
                >
                  {copied ? t("autotool.copied") : t("autotoolCfg.copyAll")}
                </button>
              )}
            </div>

            {data.requests.length === 0 ? (
              <p className="rounded-md border border-dashed border-neutral-300 px-3 py-4 text-center text-xs text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                {t("autotoolCfg.noDomains")}
              </p>
            ) : (
              <div className="max-h-96 space-y-3 overflow-auto">
                {data.requests.map((r) => (
                  <div key={r.file}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-xs font-medium text-neutral-800 dark:text-neutral-200">
                        {r.site}
                      </span>
                      <span className="shrink-0 text-xs text-neutral-400 dark:text-neutral-500">
                        {t("autotoolCfg.pageRange", {
                          from: r.start + 1,
                          to: r.start + r.row_count,
                          total: r.total,
                        })}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <a
                        href={autotoolCsvUrl(r.file)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="min-w-0 flex-1 truncate font-mono text-xs text-blue-600 hover:underline dark:text-blue-400"
                        title={autotoolCsvUrl(r.file)}
                      >
                        {autotoolCsvUrl(r.file)}
                      </a>
                      <button
                        type="button"
                        onClick={() => void copyCsvLink(r.file)}
                        className="shrink-0 rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                      >
                        {copiedFile === r.file
                          ? t("autotool.copied")
                          : t("autotoolCfg.copyCsvLink")}
                      </button>
                    </div>
                    <pre className="mt-1 overflow-auto rounded-md bg-neutral-50 p-3 text-xs leading-relaxed text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
                      {fmtRequest(r.body)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {t("autotoolCfg.keyMaskedNote")}
            </p>
          </div>

          {/* Send */}
          {data.requests.length > 0 && (
            <div className="border-t border-neutral-200 pt-4 dark:border-neutral-800">
              {data.missing_required_columns.length > 0 ? (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  {t("autotoolCfg.sendNeedsColumns")}
                </p>
              ) : !data.target_configured || !data.api_key_configured ? (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  {t("autotoolCfg.sendNeedsConfig")}
                </p>
              ) : confirming ? (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-700/60 dark:bg-amber-950/40">
                  <p className="text-xs text-amber-900 dark:text-amber-200">
                    {t("autotoolCfg.sendConfirmWarn", { n: data.page_count })}
                  </p>
                  {hasAppend && (
                    <label className="mt-2 flex cursor-pointer items-start gap-2 text-xs text-amber-900 dark:text-amber-200">
                      <input
                        type="checkbox"
                        checked={ackAppend}
                        onChange={(e) => setAckAppend(e.target.checked)}
                        className="mt-0.5 h-3.5 w-3.5"
                      />
                      <span>{t("autotoolCfg.appendAck")}</span>
                    </label>
                  )}
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => void send()}
                      disabled={sending || (hasAppend && !ackAppend)}
                      className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-60"
                    >
                      {sending ? t("autotoolCfg.sending") : t("autotoolCfg.sendConfirm")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(false)}
                      disabled={sending}
                      className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      {t("autotool.cancel")}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(true)}
                  className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
                >
                  {t("autotoolCfg.startRun", { n: data.page_count })}
                </button>
              )}
              {sendError && (
                <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
                  {sendError}
                </p>
              )}
            </div>
          )}
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
