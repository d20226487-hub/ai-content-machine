"use client";

import Link from "next/link";
import { ChangeEvent, FormEvent, useEffect, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { ProviderModelPicker } from "@/components/ProviderModelPicker";
import { ApiError } from "@/lib/api";
import { useT, type TranslationKey } from "@/lib/i18n-context";
import { listEnabledProviders } from "@/lib/generate";
import {
  deleteGdocsRun,
  importGdocs,
  listGdocsRuns,
  type GdocsImportRun,
} from "@/lib/gdocsImport";
import type { BulkFolder } from "@/lib/library";
import type { EnabledProvider } from "@/lib/types";

interface Props {
  folders: BulkFolder[];
  /** Pre-select this folder (the one the user is currently viewing). */
  defaultFolderId?: number | null;
  onClose: () => void;
  onQueued: (run: GdocsImportRun) => void;
}

export function GdocsImportModal({
  folders,
  defaultFolderId = null,
  onClose,
  onQueued,
}: Props) {
  const { t } = useT();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [folderId, setFolderId] = useState<number | null>(defaultFolderId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  // AI override (mirrors the Brain tab's picker). Null = workspace default,
  // i.e. the first-enabled provider + its default model resolved server-side.
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);

  // Recent imports — the surface for finding + clearing old/stuck runs.
  const [recent, setRecent] = useState<GdocsImportRun[]>([]);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listEnabledProviders()
      .then((p) => {
        if (!cancelled) setProviders(p);
      })
      .catch(() => {
        // Picker just shows the "no provider" hint; import can still run on
        // the workspace default if one exists.
      });
    listGdocsRuns(8)
      .then((r) => {
        if (!cancelled) setRecent(r);
      })
      .catch(() => {
        // History is a convenience — a fetch failure just hides the section.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onDeleteRun(id: number) {
    if (deletingId != null) return;
    if (!window.confirm(t("gdocsRun.deleteConfirm"))) return;
    setDeletingId(id);
    try {
      await deleteGdocsRun(id);
      setRecent((rs) => rs.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err : String(err));
    } finally {
      setDeletingId(null);
    }
  }

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    if (f && !name.trim()) {
      setName(f.name.replace(/\.[^.]+$/, ""));
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const run = await importGdocs({
        file,
        name: name.trim(),
        folderId,
        providerCode,
        model,
      });
      onQueued(run);
    } catch (err) {
      console.error("[Library] Google-Docs import failed", err);
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("gdocsImport.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("gdocsImport.subtitle")}
      </p>

      {/* How to produce the JSON — the Apps Script bridge. Collapsed by
          default so the form stays uncluttered for repeat users. */}
      <div className="mt-4 rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2 text-xs dark:border-neutral-700 dark:bg-neutral-900/40">
        <button
          type="button"
          onClick={() => setHelpOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-3 text-left font-medium text-neutral-700 dark:text-neutral-200"
        >
          <span>{t("gdocsImport.helpToggle")}</span>
          <span aria-hidden>{helpOpen ? "▴" : "▾"}</span>
        </button>
        {helpOpen && (
          <div className="mt-2 space-y-2 text-neutral-600 dark:text-neutral-400">
            <ol className="list-decimal space-y-1 pl-4">
              <li>{t("gdocsImport.step1")}</li>
              <li>{t("gdocsImport.step2")}</li>
              <li>{t("gdocsImport.step3")}</li>
              <li>{t("gdocsImport.step4")}</li>
              <li>{t("gdocsImport.step5")}</li>
            </ol>
            <div className="flex flex-wrap gap-2 pt-1">
              <a
                href="/gdocs-apps-script/Code.gs"
                download
                className="inline-flex items-center gap-1 rounded-md border border-neutral-300 bg-white px-2.5 py-1 font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("gdocsImport.downloadCode")}
              </a>
              <a
                href="/gdocs-apps-script/appsscript.json"
                download
                className="inline-flex items-center gap-1 rounded-md border border-neutral-300 bg-white px-2.5 py-1 font-medium text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("gdocsImport.downloadManifest")}
              </a>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("gdocsImport.tableName")}
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("gdocsImport.tableNamePlaceholder")}
            className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("gdocsImport.jsonFile")}
          <input
            type="file"
            accept=".json,application/json"
            onChange={onPick}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutral-900 file:px-3 file:py-2 file:text-xs file:font-medium file:text-white hover:file:bg-neutral-800 dark:file:bg-neutral-100 dark:file:text-neutral-900"
          />
          {file && (
            <span className="mt-1 inline-block text-xs text-neutral-500 dark:text-neutral-400">
              {file.name} · {(file.size / 1024).toFixed(0)} KB
            </span>
          )}
        </label>

        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("gdocsImport.folder")}
          <select
            value={folderId ?? ""}
            onChange={(e) =>
              setFolderId(e.target.value === "" ? null : Number(e.target.value))
            }
            className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          >
            <option value="">{t("gdocsImport.noFolder")}</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>

        {/* AI model used to clean meta + pair pages. Defaults to the
            workspace default; override per-import here. */}
        <div>
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("gdocsImport.aiHeading")}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t("gdocsImport.aiHelp")}
          </p>
          <ProviderModelPicker
            className="mt-2"
            providers={providers}
            providerCode={providerCode}
            model={model}
            onProviderChange={(code) => {
              setProviderCode(code);
              setModel(null);
            }}
            onModelChange={setModel}
            allowDefault
          />
        </div>

        {error != null && (
          <ErrorPanel title={t("common.importFailed")} error={error} />
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
            type="submit"
            disabled={busy || !name.trim() || !file}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {busy ? t("gdocsImport.starting") : t("gdocsImport.start")}
          </button>
        </div>
      </form>

      {/* Recent imports — open one's progress page, or clear finished/stuck
          runs from history (the table a run built is independent and kept). */}
      {recent.length > 0 && (
        <div className="mt-6 border-t border-neutral-200 pt-4 dark:border-neutral-800">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("gdocsImport.recentHeading")}
          </p>
          <ul className="space-y-0.5">
            {recent.map((r) => {
              const active = r.status === "queued" || r.status === "running";
              return (
                <li
                  key={r.id}
                  className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
                >
                  <span
                    className={"h-2 w-2 shrink-0 rounded-full " + statusDot(r.status)}
                    title={t(STATUS_KEY[r.status])}
                  />
                  <Link
                    href={`/library/import/gdocs/${r.id}`}
                    onClick={onClose}
                    className="min-w-0 flex-1 truncate text-neutral-800 hover:underline dark:text-neutral-200"
                    title={r.table_name}
                  >
                    {r.table_name}
                  </Link>
                  <span className="shrink-0 text-xs text-neutral-400 dark:text-neutral-500">
                    {new Date(r.created_at).toLocaleDateString()}
                  </span>
                  {!active && (
                    <button
                      type="button"
                      onClick={() => onDeleteRun(r.id)}
                      disabled={deletingId === r.id}
                      title={t("gdocsRun.delete")}
                      aria-label={t("gdocsRun.delete")}
                      className="shrink-0 rounded p-1 text-neutral-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-950/30 dark:hover:text-red-400"
                    >
                      ✕
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Modal>
  );
}

/** Status → dot color for the recent-imports list. */
function statusDot(status: GdocsImportRun["status"]): string {
  switch (status) {
    case "done":
      return "bg-green-500";
    case "failed":
      return "bg-red-500";
    case "cancelled":
      return "bg-neutral-400 dark:bg-neutral-500";
    default: // queued | running
      return "bg-blue-500 dark:bg-blue-400";
  }
}

/** Status → translation key (reuses the progress-page status labels). */
const STATUS_KEY: Record<GdocsImportRun["status"], TranslationKey> = {
  queued: "gdocsRun.statusQueued",
  running: "gdocsRun.statusRunning",
  done: "gdocsRun.statusDone",
  cancelled: "gdocsRun.statusCancelled",
  failed: "gdocsRun.statusFailed",
};
