"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { Pagination } from "@/components/Pagination";
import { ApiError } from "@/lib/api";
import {
  cancelAiHelperRun,
  getAiHelperRun,
  retryFailedAiHelperRun,
  revertAiHelperRun,
  type AiHelperRunDetail,
} from "@/lib/aiHelper";
import { useT } from "@/lib/i18n-context";

const PAGE_SIZE = 25;
const TERMINAL = new Set(["done", "failed", "cancelled"]);

export default function AiHelperRunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [run, setRun] = useState<AiHelperRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pageRef = useRef(page);
  pageRef.current = page;

  const load = useCallback(async () => {
    try {
      setRun(await getAiHelperRun(rid, pageRef.current, PAGE_SIZE));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, [rid]);

  useEffect(() => {
    void load();
  }, [load, page]);

  // Poll while active; stop on a terminal status.
  useEffect(() => {
    if (run && TERMINAL.has(run.status)) return;
    const h = setInterval(() => void load(), 2000);
    return () => clearInterval(h);
  }, [run, load]);

  async function act(fn: () => Promise<AiHelperRunDetail>) {
    setBusy(true);
    setError(null);
    try {
      setRun(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const pct = run && run.total > 0
    ? Math.round(((run.done + run.failed + run.skipped) / run.total) * 100)
    : 0;
  const active = run ? !TERMINAL.has(run.status) : false;
  const canRevert =
    !!run && run.status === "done" && !run.reverted_at && run.done > 0;
  const canRetry = !!run && TERMINAL.has(run.status) && run.failed > 0;

  return (
    <main className="mx-auto max-w-4xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}/ai-helper`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("aiHelper.backToTool")}
        </Link>
      </div>

      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {run?.name || t("aiHelper.runLabel", { id: rid })}
        </h1>
        {run && <LinkCheckStatusChip status={run.status} />}
      </div>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {run && (
        <>
          <div className="mt-4 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
            <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
              <span>
                {t("aiHelper.modeTag", {
                  mode: t(`aiHelper.mode.${run.mode}` as never),
                })}
                {run.reverted_at ? ` · ${t("aiHelper.reverted")}` : ""}
              </span>
              <span>{pct}%</span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
              <div
                className={`h-full ${
                  run.failed > 0 ? "bg-amber-500" : "bg-blue-600"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600 dark:text-neutral-300">
              <span>{t("aiHelper.statDone", { done: run.done, total: run.total })}</span>
              {run.failed > 0 && (
                <span className="text-red-600 dark:text-red-400">
                  {t("aiHelper.statFailed", { n: run.failed })}
                </span>
              )}
              {run.skipped > 0 && (
                <span>{t("aiHelper.statSkipped", { n: run.skipped })}</span>
              )}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {active && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(() => cancelAiHelperRun(rid))}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("aiHelper.cancelBtn")}
                </button>
              )}
              {canRetry && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void act(() => retryFailedAiHelperRun(rid))}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("aiHelper.retryBtn", { n: run.failed })}
                </button>
              )}
              {canRevert && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(t("aiHelper.revertConfirm")))
                      void act(() => revertAiHelperRun(rid));
                  }}
                  className="rounded-md border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:border-amber-700/60 dark:text-amber-300 dark:hover:bg-amber-950/40"
                >
                  {t("aiHelper.revertBtn")}
                </button>
              )}
            </div>
          </div>

          {/* Cells */}
          <section className="mt-5">
            <div className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                  <tr>
                    <th className="px-3 py-2 font-medium">{t("aiHelper.colRow")}</th>
                    <th className="px-3 py-2 font-medium">{t("aiHelper.colState")}</th>
                    <th className="px-3 py-2 font-medium">{t("aiHelper.colResult")}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                  {run.items.map((c) => (
                    <tr key={c.id} className="align-top">
                      <td className="px-3 py-2 tabular-nums text-neutral-500">
                        #{c.row_position + 1}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={
                            "rounded-full px-2 py-0.5 text-[11px] font-medium " +
                            (c.state === "done"
                              ? "bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300"
                              : c.state === "failed"
                                ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                                : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300")
                          }
                        >
                          {t(`aiHelper.cellState.${c.state}` as never)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-neutral-700 dark:text-neutral-300">
                        {c.error ? (
                          <span className="text-red-600 dark:text-red-400">{c.error}</span>
                        ) : (
                          <span className="line-clamp-3 whitespace-pre-wrap break-words font-mono text-xs">
                            {c.new_value ?? ""}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={run.items_page}
              pageSize={run.items_page_size}
              total={run.items_total}
              onPage={setPage}
            />
          </section>
        </>
      )}
    </main>
  );
}
