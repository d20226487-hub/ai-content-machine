"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { HtmlViewer } from "@/components/HtmlViewer";
import { PublishedToHistory } from "@/components/PublishedToHistory";
import { PublishToDomainModal } from "@/components/PublishToDomainModal";
import { SavedGenerationsModal } from "@/components/SavedGenerationsModal";
import { useT } from "@/lib/i18n-context";
import {
  generateSingle,
  listEnabledProviders,
  renderPrompt,
  saveGeneration,
} from "@/lib/generate";
import { getPrompt, listCategories, listPrompts } from "@/lib/prompts";
import type {
  Category,
  EnabledProvider,
  GenerateSingleResponse,
  PromptDetail,
  PromptListItem,
  SavedGeneration,
} from "@/lib/types";

export function SingleGenerator() {
  const { t } = useT();
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);

  const [search, setSearch] = useState("");
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);

  const [varValues, setVarValues] = useState<Record<string, string>>({});
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [renderedPreview, setRenderedPreview] = useState<string | null>(null);
  const [previewMissing, setPreviewMissing] = useState<string[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<GenerateSingleResponse | null>(null);

  // Save state. `savedId` !== null means the current `result` is already persisted.
  const [savedId, setSavedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);

  // Loaded-from-saved view (read-only banner above the viewer).
  const [viewingSaved, setViewingSaved] = useState<SavedGeneration | null>(null);
  const [showSavedList, setShowSavedList] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);

  // Initial load
  useEffect(() => {
    Promise.all([listPrompts({ page_size: 500 }), listCategories(), listEnabledProviders()])
      .then(([ps, cs, prv]) => {
        setPrompts(ps.items);
        setCategories(cs);
        setProviders(prv);
        // Default to the first provider that actually has a key (so Generate is enabled).
        const usable = prv.find((p) => p.has_api_key) ?? prv[0];
        if (usable) {
          setProviderCode(usable.code);
          setModel(usable.default_model);
        }
      })
      .catch((err) => {
        console.error("[Create] failed to load initial data", err);
        setError(err);
      });
  }, []);

  // Load prompt detail (with current version + variables) on selection.
  // `ignored` flag drops late results from superseded fetches: if the user
  // changes selectedPromptId twice quickly, the older request's resolution
  // would otherwise overwrite the newer one's state.
  useEffect(() => {
    if (selectedPromptId == null) {
      setSelectedPrompt(null);
      return;
    }
    let ignored = false;
    getPrompt(selectedPromptId)
      .then((p) => {
        if (!ignored) setSelectedPrompt(p);
      })
      .catch(() => {});
    return () => {
      ignored = true;
    };
  }, [selectedPromptId]);

  // Reset variable values when prompt changes
  useEffect(() => {
    if (!selectedPrompt) return;
    const fresh: Record<string, string> = {};
    for (const v of selectedPrompt.variables) fresh[v] = varValues[v] ?? "";
    setVarValues(fresh);
    setRenderedPreview(null);
    setResult(null);
    setShowPreview(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPrompt?.id]);

  // When preview is open, debounce-refresh as the user fills variables
  useEffect(() => {
    if (!showPreview || !selectedPrompt) return;
    const t = setTimeout(async () => {
      try {
        const r = await renderPrompt({
          prompt_id: selectedPrompt.id,
          variables: varValues,
        });
        setRenderedPreview(r.rendered_prompt);
        setPreviewMissing(r.missing_variables);
      } catch {
        setRenderedPreview(null);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [showPreview, varValues, selectedPrompt]);

  const filteredPrompts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return prompts;
    return prompts.filter((p) => p.name.toLowerCase().includes(q));
  }, [prompts, search]);

  const promptsByCat = useMemo(() => {
    const groups = new Map<string, PromptListItem[]>();
    const catName = (id: number | null) =>
      id == null ? t("colCfg.noFolder") : categories.find((c) => c.id === id)?.name ?? t("colCfg.noFolder");
    for (const p of filteredPrompts) {
      const k = catName(p.category_id);
      const arr = groups.get(k) ?? [];
      arr.push(p);
      groups.set(k, arr);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filteredPrompts, categories]);

  const currentProvider = providers.find((p) => p.code === providerCode);
  const noProviders = providers.length === 0;

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    if (!selectedPrompt) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setSavedId(null);
    setSaveError(null);
    setViewingSaved(null);
    try {
      const r = await generateSingle({
        prompt_id: selectedPrompt.id,
        variables: varValues,
        provider_code: providerCode,
        model,
      });
      setResult(r);
    } catch (err) {
      console.error("[Create] generation failed", err);
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    if (!result || !selectedPrompt) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveGeneration({
        prompt_id: selectedPrompt.id,
        prompt_version_number: selectedPrompt.current_version?.version_number ?? null,
        rendered_prompt: result.rendered_prompt,
        output: result.text,
        variables: varValues,
        provider_code: result.provider_used,
        model_used: result.model_used,
        finish_reason: result.finish_reason ?? null,
      });
      setSavedId(saved.id);
    } catch (err) {
      console.error("[Create] save failed", err);
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  }

  function loadSaved(s: SavedGeneration) {
    // Render the saved generation in the viewer below the form.
    setResult({
      text: s.output,
      rendered_prompt: s.rendered_prompt,
      provider_used: s.provider_code,
      model_used: s.model_used,
      finish_reason: s.finish_reason,
      missing_variables: [],
    });
    setSavedId(s.id);
    setViewingSaved(s);
    setError(null);
    setSaveError(null);
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[320px_1fr]">
      {/* Left: prompt picker */}
      <aside className="min-w-0">
        <h2 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("single.pickPrompt")}
        </h2>
        <input
          type="text"
          placeholder={t("common.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mt-2 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
        <div className="mt-3 max-h-[60vh] space-y-3 overflow-y-auto pr-1">
          {promptsByCat.length === 0 && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {t("colCfg.noPromptsMatch")}
            </p>
          )}
          {promptsByCat.map(([catName, items]) => (
            <div key={catName}>
              <p className="px-1 text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {catName}
              </p>
              <ul className="mt-1 space-y-1">
                {items.map((p) => {
                  const active = p.id === selectedPromptId;
                  return (
                    <li key={p.id}>
                      <button
                        onClick={() => setSelectedPromptId(p.id)}
                        className={
                          "block w-full truncate rounded-md px-2 py-1.5 text-left text-sm " +
                          (active
                            ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                            : "text-neutral-700 hover:bg-neutral-50 dark:text-neutral-300 dark:hover:bg-neutral-800")
                        }
                      >
                        {p.name}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </aside>

      {/* Right: form + result */}
      <section className="min-w-0">
        <div className="mb-4 flex justify-end">
          <button
            type="button"
            onClick={() => setShowSavedList(true)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("single.savedGenerations")}
          </button>
        </div>

        {/* "Select a prompt to begin" placeholder only when there's
            also nothing to view — opening a saved generation populates
            `result` without selecting a prompt (the source prompt may
            be deleted, or just not the one currently picked), and the
            old guard `!selectedPrompt` hid the loaded output behind the
            placeholder. Bug symptom: click a saved generation, nothing
            visibly happens. */}
        {!selectedPrompt && !result && (
          <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
            {t("single.selectToBegin")}
          </div>
        )}

        {selectedPrompt && (
          <>
            <header className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-900">
              <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                {selectedPrompt.name}
              </h3>
              <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                {t("prompts.versionPrefix")}{selectedPrompt.current_version?.version_number ?? "?"} ·{" "}
                {t("single.variablesCount", { count: selectedPrompt.variables.length })}
              </p>
            </header>

            <form onSubmit={onGenerate} className="mt-5 space-y-4">
              {selectedPrompt.variables.length === 0 && (
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  {t("single.noVariables")}
                </p>
              )}
              {selectedPrompt.variables.map((v) => (
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

              {/* Provider + model */}
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
                  {currentProvider && !currentProvider.has_api_key && (
                    <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
                      {t("single.providerNoKeyHint")}
                    </p>
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

              {/* Prompt preview toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowPreview((v) => !v)}
                  className="text-sm font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                >
                  {showPreview ? t("single.hidePreview") : t("single.showPreview")}
                </button>
                {showPreview && (
                  <div className="mt-2 rounded-md border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-950">
                    <p className="text-[11px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                      {t("single.willBeSent")}
                    </p>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-neutral-800 dark:text-neutral-200">
                      {renderedPreview ?? selectedPrompt.current_version?.content ?? ""}
                    </pre>
                    {previewMissing.length > 0 && (
                      <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                        {t("single.unfilledVars", { vars: previewMissing.map((m) => `{{${m}}}`).join(", ") })}
                      </p>
                    )}
                  </div>
                )}
              </div>

              {error != null && <ErrorPanel title={t("single.generationFailed")} error={error} />}

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={busy || noProviders}
                  className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
                >
                  {busy ? t("single.generating") : t("single.generate")}
                </button>
              </div>
            </form>
          </>
        )}

        {/* Result panel — intentionally OUTSIDE the `selectedPrompt &&`
            block above. Opening a saved generation populates `result`
            without changing the prompt selection (and the source prompt
            may have been deleted entirely — `viewingSaved.prompt_id`
            can be null). Gating this on `selectedPrompt` used to hide
            the loaded output behind the empty-state placeholder; the
            click did fire and state did update, but nothing rendered. */}
        {result && (
          <div className="mt-6 space-y-3">
            {viewingSaved && (
              <>
                <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200">
                  {t("single.viewingSaved")} <b>{viewingSaved.name}</b>
                  <button
                    type="button"
                    onClick={() => {
                      setResult(null);
                      setSavedId(null);
                      setViewingSaved(null);
                    }}
                    className="ml-3 underline"
                  >
                    {t("single.clear")}
                  </button>
                </div>
                <PublishedToHistory generationId={viewingSaved.id} />
              </>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("single.generatedWith", { provider: result.provider_used, model: result.model_used })}
                {result.finish_reason && ` · ${result.finish_reason}`}
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setPublishOpen(true)}
                  className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                >
                  {t("single.publishTo")}
                </button>
                {!viewingSaved && (
                  <button
                    type="button"
                    onClick={onSave}
                    disabled={saving || savedId != null}
                    className={
                      "rounded-md px-3 py-1.5 text-xs font-medium " +
                      (savedId != null
                        ? "border border-green-300 text-green-700 dark:border-green-800 dark:text-green-300"
                        : "bg-neutral-900 text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200")
                    }
                  >
                    {saving ? t("common.saving") : savedId != null ? t("single.alreadySaved") : t("common.save")}
                  </button>
                )}
              </div>
            </div>

            {saveError != null && <ErrorPanel title={t("single.saveFailed")} error={saveError} />}

            <HtmlViewer
              content={result.text}
              title={viewingSaved ? viewingSaved.name : t("single.generatedContent")}
              height="h-[28rem]"
            />
          </div>
        )}

        {showSavedList && (
          <SavedGenerationsModal
            onClose={() => setShowSavedList(false)}
            onLoad={loadSaved}
          />
        )}

        {publishOpen && result && (
          <PublishToDomainModal
            initialTitle={selectedPrompt?.name}
            initialContent={result.text}
            sourceRef={
              savedId != null
                ? { generation_id: savedId, prompt_id: selectedPrompt?.id ?? null }
                : { prompt_id: selectedPrompt?.id ?? null }
            }
            onClose={() => setPublishOpen(false)}
          />
        )}
      </section>
    </div>
  );
}
