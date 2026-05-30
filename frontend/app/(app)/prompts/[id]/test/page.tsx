"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ErrorPanel } from "@/components/ErrorPanel";
import { ApiError } from "@/lib/api";
import { generateSingle, listEnabledProviders } from "@/lib/generate";
import { getPrompt } from "@/lib/prompts";
import { useT } from "@/lib/i18n-context";
import { readTestSession, updateTestSession } from "@/lib/testSession";
import type { EnabledProvider, PromptDetail } from "@/lib/types";

/**
 * Test-prompt form. Mirrors /create's form-only page: variable inputs,
 * provider/model dropdowns, Generate. On Generate the page persists
 * the result to sessionStorage and navigates to
 * /prompts/[id]/test/output where the user can read, translate, or
 * Back-to-form. No Save / Publish — test runs are intentionally
 * throwaway, that's the whole point of having a separate flow.
 */
export default function TestPromptPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const promptId = Number(params.id);

  const [prompt, setPrompt] = useState<PromptDetail | null>(null);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [varValues, setVarValues] = useState<Record<string, string>>({});
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loadError, setLoadError] = useState<unknown>(null);

  // Hydrate from the test session (if the user is coming Back from the
  // output page) BEFORE we set provider defaults — otherwise the
  // restore would clobber what they had picked.
  useEffect(() => {
    let cancelled = false;
    Promise.all([getPrompt(promptId), listEnabledProviders()])
      .then(([p, prv]) => {
        if (cancelled) return;
        setPrompt(p);
        setProviders(prv);

        const snap = readTestSession();
        const fromSnap = snap && snap.form.promptId === promptId;
        if (fromSnap) {
          // Carry over only variables that still exist on this prompt
          // version — a prompt edit between sessions could drop one.
          const restored: Record<string, string> = {};
          for (const v of p.variables) restored[v] = snap.form.varValues[v] ?? "";
          setVarValues(restored);
          setProviderCode(snap.form.providerCode);
          setModel(snap.form.model);
        } else {
          // Fresh test: blank vars + first usable provider.
          const init: Record<string, string> = {};
          for (const v of p.variables) init[v] = "";
          setVarValues(init);
          const usable = prv.find((x) => x.has_api_key) ?? prv[0];
          if (usable) {
            setProviderCode(usable.code);
            setModel(usable.default_model);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [promptId]);

  const currentProvider = useMemo(
    () => providers.find((p) => p.code === providerCode),
    [providers, providerCode],
  );
  const noProviders = providers.length === 0;

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    if (!prompt) return;
    setBusy(true);
    setError(null);
    try {
      const r = await generateSingle({
        prompt_id: prompt.id,
        variables: varValues,
        provider_code: providerCode,
        model,
      });
      updateTestSession({
        form: {
          promptId: prompt.id,
          promptVersionNumber: prompt.current_version?.version_number ?? null,
          promptName: prompt.name,
          varValues,
          providerCode,
          model,
        },
        result: r,
        // A fresh generation invalidates any prior translations — they
        // belonged to the previous output.
        localTranslations: {},
      });
      router.push(`/prompts/${prompt.id}/test/output`);
    } catch (err) {
      console.error("[Test] generation failed", err);
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-3xl p-8">
        <ErrorPanel
          title={t("common.failedToLoad")}
          error={
            loadError instanceof ApiError ? loadError.message : String(loadError)
          }
        />
        <div className="mt-4">
          <Link
            href={`/prompts/${promptId}`}
            className="text-sm text-neutral-700 underline dark:text-neutral-300"
          >
            ← {t("test.backToPrompt")}
          </Link>
        </div>
      </main>
    );
  }

  if (!prompt) {
    return (
      <main className="mx-auto max-w-3xl p-8">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <Link
        href={`/prompts/${prompt.id}`}
        className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200"
      >
        <span aria-hidden="true">←</span> {t("test.backToPrompt")}
      </Link>

      <header className="mt-3">
        <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("test.pageTitle")}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("test.pageSubtitle")}
        </p>
      </header>

      <section className="mt-6 rounded-lg border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
        <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
          {prompt.name}
        </h2>
        <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
          {t("prompts.versionPrefix")}
          {prompt.current_version?.version_number ?? "?"} ·{" "}
          {t("single.variablesCount", { count: prompt.variables.length })}
        </p>
      </section>

      <form onSubmit={onGenerate} className="mt-5 space-y-4">
        {prompt.variables.length === 0 && (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            {t("single.noVariables")}
          </p>
        )}
        {prompt.variables.map((v) => (
          <label
            key={v}
            className="block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            <span className="font-mono">{`{{${v}}}`}</span>
            <textarea
              rows={2}
              value={varValues[v] ?? ""}
              onChange={(e) =>
                setVarValues((cur) => ({ ...cur, [v]: e.target.value }))
              }
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            />
          </label>
        ))}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("single.providerLabel")}
            {noProviders ? (
              <p className="mt-1 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                {t("single.noProviderEnabled")}
              </p>
            ) : (
              <select
                value={providerCode ?? ""}
                onChange={(e) => {
                  const code = e.target.value;
                  setProviderCode(code);
                  const p = providers.find((x) => x.code === code);
                  setModel(p?.default_model ?? null);
                }}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
              >
                {providers.map((p) => (
                  <option key={p.code} value={p.code} disabled={!p.has_api_key}>
                    {p.display_name}
                    {!p.has_api_key && ` ${t("newPrompt.providerNoApiKey")}`}
                  </option>
                ))}
              </select>
            )}
          </label>
          {!noProviders && currentProvider && (
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("single.modelLabel")}
              <select
                value={model ?? ""}
                onChange={(e) => setModel(e.target.value || null)}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
              >
                {(currentProvider.available_models.length > 0
                  ? currentProvider.available_models
                  : currentProvider.default_model
                    ? [currentProvider.default_model]
                    : []
                ).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        {error != null && (
          <ErrorPanel title={t("single.generationFailed")} error={error} />
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={busy || noProviders}
            data-testid="test-generate-btn"
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {busy ? t("single.generating") : t("test.generate")}
          </button>
        </div>
      </form>
    </main>
  );
}
