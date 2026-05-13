"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getDomainTrashRetention, setDomainTrashRetention } from "@/lib/domains";
import {
  getTrashRetention as getBulkTableTrashRetention,
  setTrashRetention as setBulkTableTrashRetention,
  type TrashRetention,
} from "@/lib/library";
import {
  getPromptTrashRetention,
  setPromptTrashRetention,
} from "@/lib/prompts";
import {
  getUserTrashRetention,
  setUserTrashRetention,
} from "@/lib/users";

/**
 * Unified retention settings for every Trash surface in the app. Each
 * soft-deletable entity carries its own `<entity>_trash_retention_days`
 * setting; the cleanup Celery task scans them independently. A value of
 * 0 disables auto-empty for that entity (manual emptying only).
 *
 * Adding a new entity = new row here + matching client lib + extending
 * `app.tasks.trash_cleanup._ENTITIES` on the backend.
 */
interface EntityState {
  /** i18n key for the label, e.g. "settings.trashRetention.bulkTables". */
  labelKey: string;
  state: TrashRetention | null;
  draft: string;
  saving: boolean;
  savedFlash: boolean;
  error: string | null;
  /** API getters / setters; kept loosely typed since the shape is uniform. */
  getter: () => Promise<TrashRetention>;
  setter: (days: number) => Promise<TrashRetention>;
}

export function TrashRetentionCard() {
  const { t } = useT();

  // Each row is a small piece of state; tracked in a flat array so we
  // can render them generically. New entities slot in here without
  // touching the JSX below.
  const [rows, setRows] = useState<EntityState[]>(() => [
    {
      labelKey: "settings.trashRetention.bulkTables",
      state: null,
      draft: "",
      saving: false,
      savedFlash: false,
      error: null,
      getter: getBulkTableTrashRetention,
      setter: setBulkTableTrashRetention,
    },
    {
      labelKey: "settings.trashRetention.domains",
      state: null,
      draft: "",
      saving: false,
      savedFlash: false,
      error: null,
      getter: getDomainTrashRetention,
      setter: setDomainTrashRetention,
    },
    {
      labelKey: "settings.trashRetention.prompts",
      state: null,
      draft: "",
      saving: false,
      savedFlash: false,
      error: null,
      getter: getPromptTrashRetention,
      setter: setPromptTrashRetention,
    },
    {
      labelKey: "settings.trashRetention.users",
      state: null,
      draft: "",
      saving: false,
      savedFlash: false,
      error: null,
      getter: getUserTrashRetention,
      setter: setUserTrashRetention,
    },
  ]);

  useEffect(() => {
    rows.forEach((row, i) => {
      row.getter()
        .then((r) => {
          setRows((cur) => {
            const next = cur.slice();
            next[i] = { ...next[i], state: r, draft: String(r.days) };
            return next;
          });
        })
        .catch((e) => {
          setRows((cur) => {
            const next = cur.slice();
            next[i] = {
              ...next[i],
              error: e instanceof ApiError ? e.message : t("common.failedToLoad"),
            };
            return next;
          });
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function update(i: number, patch: Partial<EntityState>) {
    setRows((cur) => {
      const next = cur.slice();
      next[i] = { ...next[i], ...patch };
      return next;
    });
  }

  async function onSave(i: number) {
    const row = rows[i];
    const n = Number(row.draft);
    if (!Number.isFinite(n) || n < 0 || (row.state && n > row.state.max)) {
      update(i, { error: t("settings.trashRetention.hint") });
      return;
    }
    update(i, { saving: true, error: null });
    try {
      const updated = await row.setter(Math.floor(n));
      update(i, {
        state: updated,
        draft: String(updated.days),
        savedFlash: true,
        saving: false,
      });
      setTimeout(() => update(i, { savedFlash: false }), 1500);
    } catch (e) {
      update(i, {
        saving: false,
        error: e instanceof ApiError ? e.message : t("common.actionFailed"),
      });
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("settings.trashRetention.title")}
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("settings.trashRetention.hint")}
      </p>

      <div className="mt-4 space-y-3">
        {rows.map((row, i) => (
          <div key={row.labelKey} className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              <span className="min-w-[160px] shrink-0">{t(row.labelKey as Parameters<typeof t>[0])}</span>
              <input
                type="number"
                min={0}
                max={row.state?.max ?? 3650}
                step={1}
                value={row.draft}
                onChange={(e) => update(i, { draft: e.target.value })}
                disabled={row.state === null}
                className="w-24 rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("settings.trashRetention.days")}
              </span>
            </label>
            <button
              type="button"
              onClick={() => onSave(i)}
              disabled={row.saving || row.state === null}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {row.saving ? "…" : t("common.save")}
            </button>
            {row.savedFlash && (
              <span className="text-xs text-green-600 dark:text-green-400">
                {t("settings.trashRetention.saved")}
              </span>
            )}
            {row.error && (
              <span className="basis-full text-xs text-red-600 dark:text-red-400">
                {row.error}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
