"use client";

import { useState } from "react";

import { useT, type TranslationKey } from "@/lib/i18n-context";
import type { CacheAction } from "@/lib/domainCache";

const ACTIONS: CacheAction[] = ["clear", "warm", "clear_and_warm"];

const ACTION_LABEL: Record<CacheAction, TranslationKey> = {
  clear: "cacheModal.action_clear",
  warm: "cacheModal.action_warm",
  clear_and_warm: "cacheModal.action_clear_and_warm",
};
const ACTION_HINT: Record<CacheAction, TranslationKey> = {
  clear: "cacheModal.actionHint_clear",
  warm: "cacheModal.actionHint_warm",
  clear_and_warm: "cacheModal.actionHint_clear_and_warm",
};

/**
 * Pick a cache action for the selected domains and launch a background run.
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
  onConfirm: (action: CacheAction) => void;
}) {
  const { t } = useT();
  const [action, setAction] = useState<CacheAction>("clear_and_warm");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("cacheModal.title")}
        </h2>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("cacheModal.subtitle", { count: selectedCount })}
        </p>

        <div className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
          {t("cacheModal.customOnlyNote")}
        </div>

        <fieldset className="mt-4 space-y-2" disabled={busy}>
          {ACTIONS.map((a) => (
            <label
              key={a}
              className={
                "flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm " +
                (action === a
                  ? "border-neutral-900 bg-neutral-50 dark:border-neutral-100 dark:bg-neutral-800/50"
                  : "border-neutral-200 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800/40")
              }
            >
              <input
                type="radio"
                name="cache-action"
                value={a}
                checked={action === a}
                onChange={() => setAction(a)}
                className="mt-0.5"
              />
              <span>
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {t(ACTION_LABEL[a])}
                </span>
                <span className="block text-xs text-neutral-500 dark:text-neutral-400">
                  {t(ACTION_HINT[a])}
                </span>
              </span>
            </label>
          ))}
        </fieldset>

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
            onClick={() => onConfirm(action)}
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
