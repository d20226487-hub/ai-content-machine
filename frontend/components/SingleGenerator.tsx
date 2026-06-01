"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ErrorPanel } from "@/components/ErrorPanel";
import { clearSession, readSession, updateSession } from "@/lib/createSession";
import { useT } from "@/lib/i18n-context";
import { generateSingle, listEnabledProviders } from "@/lib/generate";
import { getPrompt, listCategories, listPrompts } from "@/lib/prompts";
import type {
  Category,
  EnabledProvider,
  PromptDetail,
  PromptListItem,
} from "@/lib/types";

/**
 * The /create form. Renders just the prompt picker + variable inputs +
 * provider/model dropdowns + Generate button. The post-Generate result
 * is no longer shown here — it lives at /create/output so it can take
 * the full viewport. Hitting Generate writes the result to
 * sessionStorage and routes to /create/output; on remount this
 * component re-hydrates the form so "Back to form" feels seamless.
 *
 * Saved-generation history is still opened from this page via the
 * "Saved generations" modal; selecting one writes the session blob and
 * jumps to /create/output the same way Generate does.
 */
export function SingleGenerator() {
  const { t } = useT();
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);

  const [search, setSearch] = useState("");
  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);

  const [varValues, setVarValues] = useState<Record<string, string>>({});
  const [providerCode, setProviderCode] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  // Preview now shows the raw prompt template (with {{var}} placeholders
  // intact) rather than the rendered version with values substituted.
  // The previous behaviour ran POST /generate/render in a useEffect and
  // displayed the result, but reports surfaced that the box was
  // occasionally landing on LLM output after a generation cycle.
  // Sourcing directly from `selectedPrompt.current_version.content`
  // sidesteps that path entirely.
  const [showPreview, setShowPreview] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);


  // True once the initial sessionStorage hydration has had a chance to
  // run — used to avoid a flash where varValues is `{}` and immediately
  // gets repopulated.
  const [hydrated, setHydrated] = useState(false);

  // Initial load — categories, providers, prompts list — plus any
  // session snapshot the output page may have left behind. The provider
  // default is only set when no snapshot exists, so a Back-to-form
  // round trip preserves the user's provider choice.
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listPrompts({ page_size: 500 }),
      listCategories(),
      listEnabledProviders(),
    ])
      .then(([ps, cs, prv]) => {
        if (cancelled) return;
        setPrompts(ps.items);
        setCategories(cs);
        setProviders(prv);

        const snap = readSession();
        if (snap && snap.form.selectedPromptId != null) {
          // Restore from snapshot. selectedPromptId triggers the
          // selectedPrompt fetch below; varValues / provider / model
          // are restored eagerly so the form looks intact while the
          // PromptDetail loads.
          setSelectedPromptId(snap.form.selectedPromptId);
          setVarValues(snap.form.varValues ?? {});
          setProviderCode(snap.form.providerCode);
          setModel(snap.form.model);
        } else {
          const usable = prv.find((p) => p.has_api_key) ?? prv[0];
          if (usable) {
            setProviderCode(usable.code);
            setModel(usable.default_model);
          }
        }
        setHydrated(true);
      })
      .catch((err) => {
        console.error("[Create] failed to load initial data", err);
        setError(err);
        setHydrated(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load prompt detail (with current version + variables) on selection.
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

  // Reset / extend variable values when the selected prompt changes.
  // The snapshot-restore path above sets varValues before the prompt
  // detail arrives — when it does, we keep any values that match the
  // new prompt's variables and drop the rest. Without the hydrated
  // guard, the first effect run would wipe the just-restored values.
  useEffect(() => {
    if (!selectedPrompt) return;
    setVarValues((cur) => {
      const fresh: Record<string, string> = {};
      for (const v of selectedPrompt.variables) fresh[v] = cur[v] ?? "";
      return fresh;
    });
    setShowPreview(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPrompt?.id]);

  const filteredPrompts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return prompts;
    return prompts.filter((p) => p.name.toLowerCase().includes(q));
  }, [prompts, search]);

  const promptsByCat = useMemo(() => {
    const groups = new Map<string, PromptListItem[]>();
    const catName = (id: number | null) =>
      id == null
        ? t("colCfg.noFolder")
        : categories.find((c) => c.id === id)?.name ?? t("colCfg.noFolder");
    for (const p of filteredPrompts) {
      const k = catName(p.category_id);
      const arr = groups.get(k) ?? [];
      arr.push(p);
      groups.set(k, arr);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filteredPrompts, categories, t]);

  const currentProvider = providers.find((p) => p.code === providerCode);
  const noProviders = providers.length === 0;

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    if (!selectedPrompt) return;
    setBusy(true);
    setError(null);
    try {
      const r = await generateSingle({
        prompt_id: selectedPrompt.id,
        variables: varValues,
        provider_code: providerCode,
        model,
      });
      // Persist form + result, then jump to the dedicated output view.
      // Writing the session first means a refresh of /create/output
      // shows the result immediately without re-running the LLM.
      updateSession({
        form: {
          selectedPromptId: selectedPrompt.id,
          selectedPromptVersionNumber:
            selectedPrompt.current_version?.version_number ?? null,
          selectedPromptName: selectedPrompt.name,
          varValues,
          providerCode,
          model,
        },
        result: r,
        savedId: null,
        viewingSaved: null,
        localTranslations: {},
      });
      router.push("/create/output");
    } catch (err) {
      console.error("[Create] generation failed", err);
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function startFresh() {
    // "Clear form" — drops both local state and the persisted snapshot
    // so a subsequent Back from /create/output doesn't resurrect the
    // old form. Not auto-wired anywhere yet but used by the Saved-list
    // close path so the next session starts clean.
    clearSession();
    setSelectedPromptId(null);
    setSelectedPrompt(null);
    setVarValues({});
  }
  void startFresh; // reserved for future "New session" button

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

      {/* Right: form */}
      <section className="min-w-0">
        <div className="mb-4 flex justify-end">
          <Link
            href="/create/saved"
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("single.savedGenerations")}
          </Link>
        </div>

        {hydrated && !selectedPrompt && (
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
                {t("prompts.versionPrefix")}
                {selectedPrompt.current_version?.version_number ?? "?"} ·{" "}
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

              {/* Prompt-template preview toggle. Shows the raw template
               *  content with {{var}} placeholders intact — what the
               *  user wrote on the prompt-detail page, not the rendered
               *  version with their current variable values substituted
               *  in. */}
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
                      {t("single.promptTemplateLabel")}
                    </p>
                    <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-neutral-800 dark:text-neutral-200">
                      {selectedPrompt.current_version?.content ?? ""}
                    </pre>
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
                  className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
                >
                  {busy ? t("single.generating") : t("single.generate")}
                </button>
              </div>
            </form>
          </>
        )}

      </section>
    </div>
  );
}
