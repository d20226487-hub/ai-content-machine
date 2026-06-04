"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  cancelGdocsRun,
  deleteGdocsRun,
  getGdocsRun,
  type GdocsImportRun,
} from "@/lib/gdocsImport";

/**
 * Progress page for one Google-Docs import run.
 *
 * Polls ``GET /library/import/gdocs-runs/{id}`` every ~2s while the run is
 * active (queued / running) and stops on a terminal status. Mirrors the
 * gen-run page: status pill, progress bars, counters, plus the import-specific
 * matched/unmatched + warnings summary and a link to the built table.
 */
export default function GdocsImportRunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  const id = Number(runId);
  const { t } = useT();
  const router = useRouter();
  const [run, setRun] = useState<GdocsImportRun | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const stoppedRef = useRef(false);

  const tick = useCallback(async () => {
    try {
      const r = await getGdocsRun(id);
      setRun(r);
      setLoadError(null);
      if (r.status === "done" || r.status === "cancelled" || r.status === "failed") {
        stoppedRef.current = true;
      }
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    }
  }, [id]);

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setLoadError("Invalid run id");
      return;
    }
    stoppedRef.current = false;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loop() {
      if (cancelled) return;
      await tick();
      if (cancelled || stoppedRef.current) return;
      timer = setTimeout(loop, 2000);
    }
    void loop();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id, tick]);

  async function onCancel() {
    if (run == null || cancelling) return;
    if (!window.confirm(t("gdocsRun.cancelConfirm"))) return;
    setCancelling(true);
    try {
      await cancelGdocsRun(run.id);
      stoppedRef.current = false;
      await tick();
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCancelling(false);
    }
  }

  async function onDelete() {
    if (run == null || deleting) return;
    if (!window.confirm(t("gdocsRun.deleteConfirm"))) return;
    setDeleting(true);
    try {
      await deleteGdocsRun(run.id);
      router.push("/library");
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
      setDeleting(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <nav className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
        <Link href="/library" className="hover:underline">
          {t("library.breadcrumbRoot")}
        </Link>
        <span className="mx-1">/</span>
        <span className="text-neutral-700 dark:text-neutral-300">
          {run?.table_name ?? t("gdocsRun.title", { id })}
        </span>
      </nav>

      {loadError && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {run && (
        <RunBody
          run={run}
          cancelling={cancelling}
          onCancel={onCancel}
          deleting={deleting}
          onDelete={onDelete}
        />
      )}
    </main>
  );
}

function RunBody({
  run,
  cancelling,
  onCancel,
  deleting,
  onDelete,
}: {
  run: GdocsImportRun;
  cancelling: boolean;
  onCancel: () => void;
  deleting: boolean;
  onDelete: () => void;
}) {
  const { t } = useT();
  const isActive = run.status === "queued" || run.status === "running";

  const docsAccounted = run.docs_done + run.docs_failed;
  const docsPct =
    run.total_docs > 0
      ? Math.min(100, Math.round((docsAccounted / run.total_docs) * 100))
      : run.status === "done"
        ? 100
        : 0;
  const pagesAccounted = run.pages_matched + run.pages_unmatched;
  const pagesPct =
    run.total_pages > 0
      ? Math.min(100, Math.round((pagesAccounted / run.total_pages) * 100))
      : run.status === "done"
        ? 100
        : 0;

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {run.table_name}
          </h1>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("gdocsRun.meta", {
              when: new Date(run.created_at).toLocaleString(),
            })}
            {run.mode && ` · ${t(`gdocsRun.mode.${run.mode}` as "gdocsRun.mode.single")}`}
            {run.provider_code &&
              ` · ${t("gdocsRun.aiUsed", {
                provider: run.provider_code,
                model: run.model ?? "default",
              })}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={run.status} />
          {isActive ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={cancelling}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
            >
              {cancelling ? t("common.loading") : t("gdocsRun.cancel")}
            </button>
          ) : (
            <button
              type="button"
              onClick={onDelete}
              disabled={deleting}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60 dark:border-red-500/40 dark:text-red-300 dark:hover:bg-red-950/30"
            >
              {deleting ? t("common.loading") : t("gdocsRun.delete")}
            </button>
          )}
        </div>
      </header>

      {/* Coverage — how many planned Structure pages actually have a Doc. A big
          gap means most pages aren't written/linked yet. */}
      {run.total_structure_pages > 0 && (
        <CoverageBanner
          links={run.total_pages}
          planned={run.total_structure_pages}
          rowsBuilt={run.rows_built}
          done={run.status === "done"}
        />
      )}

      {/* Step 1 — Docs cleaned + meta extracted */}
      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 text-sm">
          <p className="font-medium text-neutral-900 dark:text-neutral-100">
            {t("gdocsRun.docsHeading")}
          </p>
          <p className="tabular-nums text-neutral-600 dark:text-neutral-400">
            {docsPct}%
          </p>
        </div>
        <ProgressBar pct={docsPct} status={run.status} />
        <div className="mt-3 grid grid-cols-3 gap-4 text-xs">
          <CounterCell label={t("gdocsRun.colDocsTotal")} value={run.total_docs} accent="neutral" />
          <CounterCell label={t("gdocsRun.colDocsDone")} value={run.docs_done} accent="green" />
          <CounterCell label={t("gdocsRun.colDocsFailed")} value={run.docs_failed} accent="red" />
        </div>
      </section>

      {/* Step 2 — Structure pages paired to Docs */}
      <section className="mt-4 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 text-sm">
          <p className="font-medium text-neutral-900 dark:text-neutral-100">
            {t("gdocsRun.pagesHeading")}
          </p>
          <p className="tabular-nums text-neutral-600 dark:text-neutral-400">
            {pagesPct}%
          </p>
        </div>
        <ProgressBar pct={pagesPct} status={run.status} />
        <div className="mt-3 grid grid-cols-3 gap-4 text-xs">
          <CounterCell label={t("gdocsRun.colPagesTotal")} value={run.total_pages} accent="neutral" />
          <CounterCell label={t("gdocsRun.colPagesMatched")} value={run.pages_matched} accent="green" />
          <CounterCell label={t("gdocsRun.colPagesUnmatched")} value={run.pages_unmatched} accent="amber" />
        </div>
      </section>

      {/* Result — link to the built table once done */}
      {run.status === "done" && run.result_table_id && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-green-300 bg-green-50 px-4 py-3 text-sm dark:border-green-500/30 dark:bg-green-950/30">
          <span className="text-green-800 dark:text-green-300">
            {t("gdocsRun.builtSummary", {
              rows: run.rows_built,
              mode: t(`gdocsRun.mode.${run.mode || "single"}` as "gdocsRun.mode.single"),
            })}
          </span>
          <Link
            href={`/library/${run.result_table_id}`}
            className="shrink-0 rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("gdocsRun.openTable")}
          </Link>
        </div>
      )}

      {run.error && (
        <pre className="mt-4 whitespace-pre-wrap rounded-md bg-red-50 px-3 py-2 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-300">
          {run.error}
        </pre>
      )}

      {/* Warnings — docs that couldn't export, pages with no matching Doc, etc. */}
      {run.warnings.length > 0 && (
        <section className="mt-4 rounded-lg border border-amber-300 bg-amber-50/60 p-4 dark:border-amber-500/30 dark:bg-amber-950/20">
          <p className="mb-2 text-sm font-medium text-amber-800 dark:text-amber-200">
            {t("gdocsRun.warningsHeading", { count: run.warnings.length })}
          </p>
          <ul className="max-h-72 space-y-1 overflow-auto text-xs text-amber-900/90 dark:text-amber-200/80">
            {run.warnings.map((w, i) => (
              <li key={i} className="border-l-2 border-amber-300 pl-2 dark:border-amber-500/40">
                {w}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function CoverageBanner({
  links,
  planned,
  rowsBuilt,
  done,
}: {
  links: number;
  planned: number;
  rowsBuilt: number;
  done: boolean;
}) {
  const { t } = useT();
  const low = links < planned / 2;
  const cls = low
    ? "border-amber-300 bg-amber-50/70 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950/20 dark:text-amber-200"
    : "border-neutral-200 bg-white text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300";
  return (
    <section className={"mt-4 rounded-lg border p-4 text-sm " + cls}>
      <p className="font-medium">
        {t("gdocsRun.coverageSummary", {
          links,
          planned,
          rows: done ? rowsBuilt : links,
        })}
      </p>
      {low && (
        <p className="mt-1 text-xs">
          {t("gdocsRun.coverageLow", { missing: planned - links })}
        </p>
      )}
    </section>
  );
}

function ProgressBar({
  pct,
  status,
}: {
  pct: number;
  status: GdocsImportRun["status"];
}) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100 dark:bg-neutral-800">
      <div
        className={
          "h-full transition-[width] duration-300 ease-out " +
          (status === "failed"
            ? "bg-red-500"
            : status === "cancelled"
              ? "bg-neutral-400 dark:bg-neutral-500"
              : "bg-blue-500 dark:bg-blue-400")
        }
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function CounterCell({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "green" | "red" | "amber" | "neutral";
}) {
  const cls =
    accent === "green"
      ? "text-green-700 dark:text-green-400"
      : accent === "red"
        ? "text-red-700 dark:text-red-400"
        : accent === "amber"
          ? "text-amber-700 dark:text-amber-400"
          : "text-neutral-700 dark:text-neutral-300";
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </p>
      <p className={"mt-0.5 text-lg font-semibold tabular-nums " + cls}>{value}</p>
    </div>
  );
}

function StatusPill({ status }: { status: GdocsImportRun["status"] }) {
  const { t } = useT();
  const cls =
    status === "running" || status === "queued"
      ? "bg-blue-50 text-blue-800 ring-blue-300 dark:bg-blue-950/40 dark:text-blue-300 dark:ring-blue-500/30"
      : status === "done"
        ? "bg-green-50 text-green-800 ring-green-300 dark:bg-green-950/40 dark:text-green-300 dark:ring-green-500/30"
        : status === "cancelled"
          ? "bg-neutral-100 text-neutral-700 ring-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-600"
          : "bg-red-50 text-red-800 ring-red-300 dark:bg-red-950/40 dark:text-red-300 dark:ring-red-500/30";
  const label =
    status === "queued"
      ? t("gdocsRun.statusQueued")
      : status === "running"
        ? t("gdocsRun.statusRunning")
        : status === "done"
          ? t("gdocsRun.statusDone")
          : status === "cancelled"
            ? t("gdocsRun.statusCancelled")
            : t("gdocsRun.statusFailed");
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-3 py-0.5 text-xs font-medium ring-1 ring-inset " +
        cls
      }
    >
      {label}
    </span>
  );
}
