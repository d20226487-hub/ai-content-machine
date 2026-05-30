"use client";

import { useEffect, useState } from "react";

import { ProviderModelPicker } from "@/components/ProviderModelPicker";
import { ApiError } from "@/lib/api";
import {
  getBrainPrompts,
  updateTranslateConfig,
  type TranslatePromptConfig,
} from "@/lib/brain";
import { listEnabledProviders } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import type { EnabledProvider } from "@/lib/types";

/**
 * Brain tab — admin-editable system prompts that power on-demand
 * actions in the rest of the app. Today the only entry is `translate`
 * (powers the Translate button in the bulk-table cell editor); the
 * card is structured so adding more prompts later is just another
 * stacked section.
 */
export function BrainCard() {
  const { t } = useT();
  const [cfg, setCfg] = useState<TranslatePromptConfig | null>(null);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([getBrainPrompts(), listEnabledProviders()])
      .then(([brain, provs]) => {
        setCfg(brain.translate);
        setProviders(provs);
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [t]);

  async function save() {
    if (!cfg) return;
    setSaving(true);
    setSaveError(null);
    try {
      const next = await updateTranslateConfig({
        prompt: cfg.prompt.trim(),
        provider_code: cfg.provider_code || null,
        model: cfg.model || null,
        default_target_language:
          cfg.default_target_language.trim().toLowerCase() || "ru",
      });
      setCfg(next);
      setSavedAt(Date.now());
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : t("common.somethingWentWrong"));
    } finally {
      setSaving(false);
    }
  }

  if (loadError) {
    return (
      <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
        {loadError}
      </p>
    );
  }

  if (!cfg) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        {t("common.loading")}
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-6 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {t("brain.translateTitle")}
          </h2>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("brain.translateSubtitle")}
          </p>
        </div>
        {savedAt && !saving && (
          <span className="shrink-0 text-xs text-green-700 dark:text-green-400">
            {t("common.saved")}
          </span>
        )}
      </div>

      <div className="mt-5 space-y-5">
        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("brain.promptLabel")}
          <textarea
            value={cfg.prompt}
            onChange={(e) => setCfg({ ...cfg, prompt: e.target.value })}
            rows={10}
            spellCheck={false}
            className="mt-1 block w-full rounded-md border border-neutral-300 bg-white p-3 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          <span className="mt-1 block text-xs font-normal text-neutral-500 dark:text-neutral-400">
            {t("brain.promptHint")}
          </span>
        </label>

        <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("brain.defaultLangLabel")}
          <input
            type="text"
            value={cfg.default_target_language}
            onChange={(e) =>
              setCfg({ ...cfg, default_target_language: e.target.value })
            }
            placeholder="ru"
            maxLength={16}
            className="mt-1 block w-32 rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <span className="mt-1 block text-xs font-normal text-neutral-500 dark:text-neutral-400">
            {t("brain.defaultLangHint")}
          </span>
        </label>

        <div>
          <p className="mb-1 text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("brain.providerLabel")}
          </p>
          <ProviderModelPicker
            providers={providers}
            providerCode={cfg.provider_code}
            model={cfg.model}
            onProviderChange={(code) =>
              setCfg({ ...cfg, provider_code: code, model: null })
            }
            onModelChange={(m) => setCfg({ ...cfg, model: m })}
            allowDefault
          />
          <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
            {t("brain.providerHint")}
          </p>
        </div>
      </div>

      {saveError && (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {saveError}
        </p>
      )}

      <div className="mt-6 flex justify-end">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
    </div>
  );
}
