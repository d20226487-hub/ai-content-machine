"use client";

import { useT } from "@/lib/i18n-context";

/**
 * Confirm clearing the cache for the selected domains and launch a background
 * run. Clear is the only action (warming was removed — it overloaded sites).
 * Only Custom-CMS domains are affected — the parent passes the raw selection
 * count; the backend filters out WordPress / unavailable domains and reports
 * them as "skipped" on the run's progress page.
 */
export function CacheActionModal({
  selectedCount,
  busy,
  error,
  onClose,
  onConfirm,
}: {
  selectedCount: number;
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const { t } = useT();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("cacheModal.title")}
        </h2>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("cacheModal.subtitle", { count: selectedCount })}
        </p>

        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-300">
          {t("cacheModal.actionHint_clear")}
        </p>

        <div className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          {t("cacheModal.customOnlyNote")}
        </div>

        {error && (
          <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {busy ? t("common.loading") : t("cacheModal.run")}
          </button>
        </div>
      </div>
    </div>
  );
}
