"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getGenerationDefaults,
  setGenerationDefaults,
  type GenerationDefaults,
} from "@/lib/settings";

/** Mirrors the backend clamp in schemas/generation.py. */
const MAX_TOKENS_CEILING = 200000;

export function GenerationDefaultsCard() {
  const { t } = useT();
  const [values, setValues] = useState<GenerationDefaults | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    getGenerationDefaults()
      .then(setValues)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [t]);

  async function onSave() {
    if (!values) return;
    setSaving(true);
    setLoadError(null);
    try {
      const next = await setGenerationDefaults(values);
      setValues(next);
      setSavedAt(Date.now());
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("users.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  // null = "send nothing, use the model's default"; the checkbox toggles
  // between that and an explicit numeric budget (0 = thinking off).
  const thinkingEnabled = values?.thinking_budget !== null;

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {t("settings.generationDefaults")}
      </h2>
      <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
        {t("settings.generationDefaultsHint")}
      </p>

      {loadError && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </p>
      )}

      {values && (
        <>
          <label className="mt-4 block max-w-xs">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("settings.maxOutputTokens")}
            </span>
            <input
              type="number"
              step={256}
              min={1}
              max={MAX_TOKENS_CEILING}
              value={values.max_output_tokens}
              onChange={(e) =>
                setValues({ ...values, max_output_tokens: Number(e.target.value) })
              }
              className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
              {t("settings.maxOutputTokensHint")}
            </span>
          </label>

          <div className="mt-5 border-t border-neutral-200 pt-4 dark:border-neutral-800">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={thinkingEnabled}
                onChange={(e) =>
                  setValues({
                    ...values,
                    thinking_budget: e.target.checked ? 0 : null,
                  })
                }
              />
              <span className="text-sm text-neutral-700 dark:text-neutral-300">
                {t("settings.thinkingBudgetEnable")}
              </span>
            </label>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              {t("settings.thinkingBudgetHint")}
            </p>

            {thinkingEnabled && (
              <label className="mt-3 block max-w-xs">
                <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {t("settings.thinkingBudget")}
                </span>
                <input
                  type="number"
                  step={256}
                  min={0}
                  max={MAX_TOKENS_CEILING}
                  value={values.thinking_budget ?? 0}
                  onChange={(e) =>
                    setValues({ ...values, thinking_budget: Number(e.target.value) })
                  }
                  className="block w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
                <span className="mt-1 block text-xs text-neutral-500 dark:text-neutral-400">
                  {t("settings.thinkingBudgetZeroHint")}
                </span>
              </label>
            )}
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            {savedAt && Date.now() - savedAt < 4000 && (
              <span className="text-xs text-green-700 dark:text-green-400">
                {t("common.savedDot")}
              </span>
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
