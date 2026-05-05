"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT, type TranslationKey } from "@/lib/i18n-context";
import {
  getPublishDefaults,
  setPublishDefaults,
  type PublishDefaults,
} from "@/lib/publish";

const FIELDS: Array<{
  key: keyof PublishDefaults;
  labelKey: TranslationKey;
  step?: number;
}> = [
  { key: "requests_per_minute", labelKey: "settings.publishDefaultsRpm", step: 1 },
  { key: "max_concurrency", labelKey: "settings.maxConcurrency", step: 1 },
  { key: "inter_request_delay_ms", labelKey: "settings.delayMs", step: 50 },
  { key: "retry_max_attempts", labelKey: "settings.retryMax", step: 1 },
  { key: "backoff_base_ms", labelKey: "settings.backoffBase", step: 50 },
  { key: "backoff_jitter_ms", labelKey: "settings.backoffJitter", step: 50 },
];

export function PublishDefaultsCard() {
  const { t } = useT();
  const [values, setValues] = useState<PublishDefaults | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    getPublishDefaults()
      .then(setValues)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [t]);

  async function onSave() {
    if (!values) return;
    setSaving(true);
    try {
      const next = await setPublishDefaults(values);
      setValues(next);
      setSavedAt(Date.now());
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("users.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("settings.publishDefaults")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("settings.publishDefaultsHint")}
      </p>

      {loadError && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {values && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {FIELDS.map((f) => (
              <label key={f.key} className="block">
                <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {t(f.labelKey)}
                </span>
                <input
                  type="number"
                  step={f.step ?? 1}
                  min={0}
                  value={values[f.key] as number}
                  onChange={(e) =>
                    setValues({ ...values, [f.key]: Number(e.target.value) })
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
              </label>
            ))}

            <label className="col-span-2 flex items-center gap-2 pt-2">
              <input
                type="checkbox"
                checked={values.respect_retry_after}
                onChange={(e) =>
                  setValues({ ...values, respect_retry_after: e.target.checked })
                }
              />
              <span className="text-sm text-neutral-700 dark:text-neutral-300">
                {t("settings.respectRetryAfterHint")}
              </span>
            </label>
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            {savedAt && Date.now() - savedAt < 4000 && (
              <span className="text-xs text-green-700 dark:text-green-400">{t("common.savedDot")}</span>
            )}
            <button
              onClick={onSave}
              disabled={saving}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {saving ? t("common.saving") : t("settings.saveDefaults")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
