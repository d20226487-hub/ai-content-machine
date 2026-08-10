"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ErrorPanel } from "@/components/ErrorPanel";
import { PromptPreview } from "@/components/PromptPreview";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { generateSingle, listEnabledProviders } from "@/lib/generate";
import { markPendingNav } from "@/lib/pendingNav";
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
  const { user } = useAuth();
  const promptId = Number(params.id);

  const [prompt, setPrompt] = useState<PromptDetail | null>(null);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [varValues, setVarValues] = useState<Record<string, string>>({});
  // Variable whose textarea is focused — highlights its spans in the preview.
  const [activeVar, setActiveVar] = useState<string | null>(null);
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [grounding, setGrounding] = useState(false);
  // A result for THIS prompt already sitting in the session — either from a
  // Back-to-form, or from a run whose navigation never landed. Surfaced as an
  // "open last result" link so a paid generation is never stranded.
  const [lastRun, setLastRun] = useState<{
    at: string | null;
    by: string | null;
  } | null>(null);

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
        if (fromSnap && snap.result) {
          setLastRun({
            at: snap.form.generatedAt ?? null,
            by: snap.form.generatedBy ?? null,
          });
        }
        if (fromSnap) {
          // Carry over only variables that still exist on this prompt
          // version — a prompt edit between sessions could drop one.
          const restored: Record<string, string> = {};
          for (const v of p.variables) restored[v] = snap.form.varValues[v] ?? "";
          setVarValues(restored);
          setProviderCode(snap.form.providerCode);
          setModel(snap.form.model);
          setGrounding(snap.form.grounding ?? false);
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

  // Grounding is wired only on the Vertex Gemini path — mirror the backend
  // rule (api/generate.py) so the toggle is offered only when the run really
  // would be grounded. The effective model falls back to the provider default,
  // exactly as the server resolves it.
  const effectiveModel = (
    model ??
    currentProvider?.default_model ??
    ""
  ).toLowerCase();
  const groundingSupported =
    providerCode === "vertex" && !effectiveModel.startsWith("claude");
  // Guard against a stale `true` after switching to an unsupported
  // provider/model — sending it would 400.
  const groundingActive = grounding && groundingSupported;

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
        grounding: groundingActive ? "google_search" : null,
      });
      updateTestSession({
        form: {
          promptId: prompt.id,
          promptVersionNumber: prompt.current_version?.version_number ?? null,
          promptName: prompt.name,
          varValues,
          providerCode,
          model,
          grounding: groundingActive,
          generatedAt: new Date().toISOString(),
          generatedBy: user ? user.full_name || user.email : null,
        },
        result: r,
        // A fresh generation invalidates any prior translations — they
        // belonged to the previous output.
        localTranslations: {},
      });
      // Mark the destination so a chunk-load failure during this push recovers
      // to the output page instead of reloading the form and stranding the
      // (already paid for) result.
      const dest = `/prompts/${prompt.id}/test/output`;
      markPendingNav(dest);
      router.push(dest);
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

  const promptContent = prompt.current_version?.content ?? "";
  const filledCount = prompt.variables.filter(
    (v) => (varValues[v] ?? "").trim() !== "",
  ).length;

  return (
    <main className="mx-auto max-w-7xl p-8">
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

      {/* A finished run for this prompt is still in the session — offer it
       *  rather than making the user re-generate (and re-pay). */}
      {lastRun && (
        <Link
          href={`/prompts/${prompt.id}/test/output`}
          data-testid="test-open-last-result"
          className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 hover:bg-blue-100 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-100 dark:hover:bg-blue-950/50"
        >
          <span className="font-medium">{t("test.openLastResult")}</span>
          {(lastRun.at || lastRun.by) && (
            <span className="text-xs text-blue-700 dark:text-blue-300">
              {[
                lastRun.at ? new Date(lastRun.at).toLocaleString() : null,
                lastRun.by,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          )}
          <span aria-hidden="true" className="ml-auto">
            →
          </span>
        </Link>
      )}

      {/* Split view: variable form on the left, the prompt those variables
       *  land in on the right. Stacks to one column below lg. */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2 lg:items-start">
        <form onSubmit={onGenerate} className="space-y-4">
          <section className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {t("test.varsHeading")}
              </h2>
              {prompt.variables.length > 0 && (
                <span className="shrink-0 text-xs text-neutral-500 dark:text-neutral-400">
                  {t("test.varsFilled", {
                    filled: filledCount,
                    total: prompt.variables.length,
                  })}
                </span>
              )}
            </div>

            {prompt.variables.length === 0 ? (
              <p className="mt-3 text-sm text-neutral-500 dark:text-neutral-400">
                {t("single.noVariables")}
              </p>
            ) : (
              <div className="mt-3 space-y-4">
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
                      onFocus={() => setActiveVar(v)}
                      onBlur={() => setActiveVar(null)}
                      className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
                    />
                  </label>
                ))}
              </div>
            )}
          </section>

        <div className="grid gap-4 rounded-lg border border-neutral-200 bg-white p-5 shadow-sm sm:grid-cols-2 dark:border-neutral-800 dark:bg-neutral-900">
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

          {/* Grounding (Google Search). Vertex + Gemini only — the checkbox is
           *  disabled elsewhere with a reason, mirroring the API's rule. */}
          {!noProviders && (
            <div className="sm:col-span-2">
              <label
                className={
                  "flex items-start gap-2 text-sm " +
                  (groundingSupported
                    ? "text-neutral-700 dark:text-neutral-300"
                    : "cursor-not-allowed text-neutral-400 dark:text-neutral-500")
                }
              >
                <input
                  type="checkbox"
                  checked={groundingActive}
                  disabled={!groundingSupported}
                  onChange={(e) => setGrounding(e.target.checked)}
                  data-testid="test-grounding-toggle"
                  className="mt-0.5 h-4 w-4 rounded border-neutral-300 disabled:opacity-50 dark:border-neutral-600"
                />
                <span>
                  <span className="font-medium">{t("test.groundingLabel")}</span>
                  <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
                    {groundingSupported
                      ? t("test.groundingHint")
                      : t("test.groundingUnsupported")}
                  </span>
                </span>
              </label>
            </div>
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

      {/* Right pane: the prompt itself, with each variable rendered in place —
       *  filled values green, still-empty placeholders amber (those reach the
       *  model as literal {{text}}). Sticky so it stays in view while the
       *  user works down a long variable list. */}
      <aside className="rounded-lg border border-neutral-200 bg-white shadow-sm lg:sticky lg:top-6 dark:border-neutral-800 dark:bg-neutral-900">
        <div className="border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
            {prompt.name}
          </h2>
          <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t("prompts.versionPrefix")}
            {prompt.current_version?.version_number ?? "?"} ·{" "}
            {t("single.variablesCount", { count: prompt.variables.length })}
          </p>
          {prompt.variables.length > 0 && (
            <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-neutral-500 dark:text-neutral-400">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-sm bg-emerald-200 dark:bg-emerald-800" />
                {t("test.legendFilled")}
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-200 dark:bg-amber-800" />
                {t("test.legendEmpty")}
              </span>
            </p>
          )}
        </div>
        <div className="max-h-[65vh] overflow-auto p-5">
          {promptContent.trim() === "" ? (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              {t("test.previewEmpty")}
            </p>
          ) : (
            <PromptPreview
              content={promptContent}
              values={varValues}
              activeVar={activeVar}
            />
          )}
        </div>
      </aside>
      </div>
    </main>
  );
}
