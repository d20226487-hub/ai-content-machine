"use client";

import { useEffect, useState } from "react";

import { ProviderModelPicker } from "@/components/ProviderModelPicker";
import { ApiError } from "@/lib/api";
import {
  getBrainPrompts,
  updateFixLinksConfig,
  updateTranslateConfig,
  type FixLinksPromptConfig,
  type TranslatePromptConfig,
} from "@/lib/brain";
import { listEnabledProviders } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import type { EnabledProvider } from "@/lib/types";

/**
 * Brain tab — admin-editable system prompts that power on-demand actions
 * in the rest of the app. Two prompts today:
 *   • translate — the Translate button in the bulk-table cell editor
 *   • fix_links — the Link Checker's AI fix pass
 * Each section is self-contained; adding more later is just another block.
 */
export function BrainCard() {
  const { t } = useT();
  const [translate, setTranslate] = useState<TranslatePromptConfig | null>(null);
  const [fixLinks, setFixLinks] = useState<FixLinksPromptConfig | null>(null);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getBrainPrompts(), listEnabledProviders()])
      .then(([brain, provs]) => {
        setTranslate(brain.translate);
        setFixLinks(brain.fix_links);
        setProviders(provs);
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [t]);

  if (loadError) {
    return (
      <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
        {loadError}
      </p>
    );
  }

  if (!translate || !fixLinks) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        {t("common.loading")}
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Translate */}
      <PromptSection
        title={t("brain.translateTitle")}
        subtitle={t("brain.translateSubtitle")}
        prompt={translate.prompt}
        onPromptChange={(p) => setTranslate({ ...translate, prompt: p })}
        providerCode={translate.provider_code}
        model={translate.model}
        onProviderChange={(code) =>
          setTranslate({ ...translate, provider_code: code, model: null })
        }
        onModelChange={(m) => setTranslate({ ...translate, model: m })}
        providers={providers}
        extra={
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("brain.defaultLangLabel")}
            <input
              type="text"
              value={translate.default_target_language}
              onChange={(e) =>
                setTranslate({
                  ...translate,
                  default_target_language: e.target.value,
                })
              }
              placeholder="ru"
              maxLength={16}
              className="mt-1 block w-32 rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            />
            <span className="mt-1 block text-xs font-normal text-neutral-500 dark:text-neutral-400">
              {t("brain.defaultLangHint")}
            </span>
          </label>
        }
        onSave={() =>
          updateTranslateConfig({
            prompt: translate.prompt.trim(),
            provider_code: translate.provider_code || null,
            model: translate.model || null,
            default_target_language:
              translate.default_target_language.trim().toLowerCase() || "ru",
          }).then(setTranslate)
        }
      />

      {/* Fix links */}
      <PromptSection
        title={t("brain.fixLinksTitle")}
        subtitle={t("brain.fixLinksSubtitle")}
        prompt={fixLinks.prompt}
        onPromptChange={(p) => setFixLinks({ ...fixLinks, prompt: p })}
        providerCode={fixLinks.provider_code}
        model={fixLinks.model}
        onProviderChange={(code) =>
          setFixLinks({ ...fixLinks, provider_code: code, model: null })
        }
        onModelChange={(m) => setFixLinks({ ...fixLinks, model: m })}
        providers={providers}
        onSave={() =>
          updateFixLinksConfig({
            prompt: fixLinks.prompt.trim(),
            provider_code: fixLinks.provider_code || null,
            model: fixLinks.model || null,
          }).then(setFixLinks)
        }
      />
    </div>
  );
}

function PromptSection<T>({
  title,
  subtitle,
  prompt,
  onPromptChange,
  providerCode,
  model,
  onProviderChange,
  onModelChange,
  providers,
  extra,
  onSave,
}: {
  title: string;
  subtitle: string;
  prompt: string;
  onPromptChange: (p: string) => void;
  providerCode: string | null;
  model: string | null;
  onProviderChange: (code: string | null) => void;
  onModelChange: (m: string | null) => void;
  providers: EnabledProvider[];
  extra?: React.ReactNode;
  onSave: () => Promise<T>;
}) {
  const { t } = useT();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave();
      setSavedAt(Date.now());
    } catch (err) {
      setSaveError(
        err instanceof ApiError ? err.message : t("common.somethingWentWrong"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-6 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {title}
          </h2>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {subtitle}
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
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            rows={10}
            spellCheck={false}
            className="mt-1 block w-full rounded-md border border-neutral-300 bg-white p-3 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          <span className="mt-1 block text-xs font-normal text-neutral-500 dark:text-neutral-400">
            {t("brain.promptHint")}
          </span>
        </label>

        {extra}

        <div>
          <p className="mb-1 text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("brain.providerLabel")}
          </p>
          <ProviderModelPicker
            providers={providers}
            providerCode={providerCode}
            model={model}
            onProviderChange={onProviderChange}
            onModelChange={onModelChange}
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
