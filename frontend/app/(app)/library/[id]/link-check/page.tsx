"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { RunRowActions } from "@/components/RunRowActions";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable } from "@/lib/library";
import {
  deleteLinkCheckRun,
  listLinkCheckRuns,
  renameLinkCheckRun,
  startLinkCheck,
  type LinkCheckRun,
} from "@/lib/linkCheck";
import type { BulkTable } from "@/lib/types";

export default function LinkCheckPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tableId = Number(id);
  const { t } = useT();

  const [table, setTable] = useState<BulkTable | null>(null);
  const [columnIds, setColumnIds] = useState<Set<number>>(new Set());
  const [checkJuxtapose, setCheckJuxtapose] = useState(false);
  const [checkCrawl, setCheckCrawl] = useState(true);
  const [includeOk, setIncludeOk] = useState(false);
  const [expectedColumnIds, setExpectedColumnIds] = useState<Set<number>>(
    new Set(),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<LinkCheckRun[]>([]);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId).then(setTable).catch((e) => setError(String(e)));
  }, [tableId]);

  const loadRuns = useCallback(() => {
    listLinkCheckRuns(tableId).then(setRuns).catch(() => {});
  }, [tableId]);
  useEffect(() => loadRuns(), [loadRuns]);

  const columns = table?.columns ?? [];
  const canRun =
    columnIds.size > 0 &&
    (checkJuxtapose || checkCrawl) &&
    (!checkJuxtapose || expectedColumnIds.size > 0);

  function toggleSet(
    setter: React.Dispatch<React.SetStateAction<Set<number>>>,
    cid: number,
  ) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  }

  async function run() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      const r = await startLinkCheck(tableId, {
        column_ids: Array.from(columnIds),
        expected_column_ids: checkJuxtapose ? Array.from(expectedColumnIds) : [],
        check_juxtapose: checkJuxtapose,
        check_crawl: checkCrawl,
        include_ok: checkCrawl ? includeOk : false,
      });
      window.location.href = `/library/${tableId}/link-check/runs/${r.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("linkCheck.backToTable")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("linkCheck.title")}
      </h1>
      {table && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("linkCheck.onTable", { name: table.name })}
        </p>
      )}

      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        {/* columns to scan */}
        <div>
          <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("linkCheck.columnsLabel")}
          </span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {columns.map((c) => {
              const on = columnIds.has(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => toggleSet(setColumnIds, c.id)}
                  className={
                    "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                    (on
                      ? "bg-blue-600 text-white ring-blue-600"
                      : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                  }
                >
                  {c.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* which checks */}
        <div className="mt-4 grid gap-2">
          <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("linkCheck.checksLabel")}
          </span>
          <Toggle
            checked={checkCrawl}
            onChange={setCheckCrawl}
            label={t("linkCheck.optCrawl")}
            hint={t("linkCheck.optCrawlHint")}
          />
          {checkCrawl && (
            <div className="ml-6">
              <Toggle
                checked={includeOk}
                onChange={setIncludeOk}
                label={t("linkCheck.optIncludeOk")}
                hint={t("linkCheck.optIncludeOkHint")}
              />
            </div>
          )}
          <Toggle
            checked={checkJuxtapose}
            onChange={setCheckJuxtapose}
            label={t("linkCheck.optJuxtapose")}
            hint={t("linkCheck.optJuxtaposeHint")}
          />
          {checkJuxtapose && (
            <div className="ml-6 mt-1">
              <span className="text-xs text-neutral-600 dark:text-neutral-400">
                {t("linkCheck.expectedLabel")}
              </span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {columns.map((c) => {
                  const on = expectedColumnIds.has(c.id);
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => toggleSet(setExpectedColumnIds, c.id)}
                      className={
                        "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                        (on
                          ? "bg-violet-600 text-white ring-violet-600"
                          : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                      }
                    >
                      {c.name}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="mt-4">
          <button
            type="button"
            disabled={!canRun || busy}
            onClick={run}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("linkCheck.checkBtn")}
          </button>
        </div>
      </section>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {runs.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("linkCheck.historyHeading")}
          </h2>
          <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {runs.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/library/${tableId}/link-check/runs/${r.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-300">
                    {r.name || t("linkCheck.runLabel", { id: r.id })}
                    <span className="ml-2 text-xs text-neutral-400">
                      {new Date(r.created_at).toLocaleString()}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    <LinkCheckStatusChip status={r.status} />
                    {(r.broken_count + r.omitted_count + r.hallucinated_count) >
                      0 && (
                      <span className="text-red-600 dark:text-red-400">
                        {t("linkCheck.violCount", {
                          n:
                            r.broken_count +
                            r.omitted_count +
                            r.hallucinated_count,
                        })}
                      </span>
                    )}
                    <RunRowActions
                      name={r.name}
                      canDelete={r.status !== "queued" && r.status !== "running"}
                      onRename={async (n) => {
                        await renameLinkCheckRun(r.id, n);
                        loadRuns();
                      }}
                      onDelete={async () => {
                        await deleteLinkCheckRun(r.id);
                        loadRuns();
                      }}
                    />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm text-neutral-700 dark:text-neutral-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
      />
      <span>
        {label}
        {hint && (
          <span className="block text-xs text-neutral-400 dark:text-neutral-500">
            {hint}
          </span>
        )}
      </span>
    </label>
  );
}
