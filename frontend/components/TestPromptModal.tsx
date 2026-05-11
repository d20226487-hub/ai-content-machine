"use client";

import { useEffect, useMemo, useState } from "react";

import { HtmlViewer } from "@/components/HtmlViewer";
import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { generateSingle, listEnabledProviders } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import type { EnabledProvider, GenerateSingleResponse, PromptDetail } from "@/lib/types";

interface Props {
  prompt: PromptDetail;
  onClose: () => void;
}

/**
 * Quick "Test" sandbox for a prompt — open from the prompt detail page.
 *
 * No save, no publish, no saved-generation entry. Just: fill the variables,
 * pick a provider/model, generate, see the output. The point is to let an
 * editor sanity-check a prompt without leaving to /create.
 *
 * Internally re-uses POST /generate/single, the same endpoint Single mode
 * uses, so behavior matches what users see in production.
 */
export function TestPromptModal({ prompt, onClose }: Props) {
  const { t } = useT();

  const [providers, setProviders] = useState<EnabledProvider[] | null>(null);
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);

  const [varValues, setVarValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const v of prompt.variables) init[v] = "";
    return init;
  });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateSingleResponse | null>(null);

  // Load enabled providers; default to first one with a key.
  useEffect(() => {
    let ignored = false;
    listEnabledProviders()
      .then((list) => {
        if (ignored) return;
        setProviders(list);
        const firstUsable = list.find((p) => p.has_api_key) ?? list[0] ?? null;
        if (firstUsable) {
          setProviderCode(firstUsable.code);
          setModel(firstUsable.default_model ?? firstUsable.available_models[0] ?? null);
        }
      })
      .catch((e) => {
        if (!ignored) setError(e instanceof ApiError ? e.message : t("test.failedLoadProviders"));
      });
    return () => {
      ignored = true;
    };
  }, [t]);

  const selectedProvider = useMemo(
    () => providers?.find((p) => p.code === providerCode) ?? null,
    [providers, providerCode],
  );

  // When provider changes, default model to the new provider's default.
  useEffect(() => {
    if (!selectedProvider) return;
    const m = selectedProvider.default_model ?? selectedProvider.available_models[0] ?? null;
    setModel(m);
  }, [selectedProvider]);

  const missingVars = useMemo(
    () => prompt.variables.filter((v) => !varValues[v]?.trim()),
    [prompt.variables, varValues],
  );

  async function onGenerate() {
    if (!providerCode || !model) {
      setError(t("test.pickProviderModel"));
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await generateSingle({
        prompt_id: prompt.id,
        version_number: prompt.current_version?.version_number ?? null,
        variables: varValues,
        provider_code: providerCode,
        model,
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("test.generateFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-3xl">
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {t("test.title", { name: prompt.name })}
          </h2>
          <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t("test.subtitle")}
          </p>
        </div>

        {/* Variables */}
        {prompt.variables.length === 0 ? (
          <p className="rounded-md bg-neutral-50 px-3 py-2 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
            {t("test.noVariables")}
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {prompt.variables.map((v) => (
              <label key={v} className="block">
                <span className="mb-0.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  {`{{${v}}}`}
                </span>
                <textarea
                  value={varValues[v] ?? ""}
                  onChange={(e) => setVarValues((cur) => ({ ...cur, [v]: e.target.value }))}
                  rows={2}
                  className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
              </label>
            ))}
          </div>
        )}

        {/* Provider + model */}
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-0.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("test.provider")}
            </span>
            <select
              value={providerCode ?? ""}
              onChange={(e) => setProviderCode(e.target.value || null)}
              className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              {(providers ?? []).map((p) => (
                <option key={p.code} value={p.code} disabled={!p.has_api_key}>
                  {p.display_name}
                  {!p.has_api_key && t("test.noKey")}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-0.5 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("test.model")}
            </span>
            <select
              value={model ?? ""}
              onChange={(e) => setModel(e.target.value || null)}
              disabled={!selectedProvider}
              className="block w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            >
              {(selectedProvider?.available_models ?? []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        </div>

        {missingVars.length > 0 && !busy && !result && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            {t("test.missingHint", { vars: missingVars.join(", ") })}
          </p>
        )}

        {error && (
          <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="border-t border-neutral-200 pt-3 dark:border-neutral-800">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("test.resultMeta", {
                  provider: result.provider_used,
                  model: result.model_used,
                })}
              </span>
            </div>
            <HtmlViewer content={result.text} height="h-72" />
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("common.close")}
          </button>
          <button
            type="button"
            onClick={onGenerate}
            disabled={busy || !providerCode || !model}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? t("test.generating") : t("test.generate")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
