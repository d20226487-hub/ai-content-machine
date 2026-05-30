"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ErrorPanel } from "@/components/ErrorPanel";
import { HtmlViewer } from "@/components/HtmlViewer";
import { PublishedToHistory } from "@/components/PublishedToHistory";
import { PublishToDomainModal } from "@/components/PublishToDomainModal";
import { TranslationPanel } from "@/components/TranslationPanel";
import {
  getBrainPrompts,
  translateGeneration,
  translateRawText,
} from "@/lib/brain";
import {
  type CreateSession,
  clearSession,
  updateSession,
} from "@/lib/createSession";
import { saveGeneration } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import type { CellTranslation, SavedGeneration } from "@/lib/types";

interface Props {
  session: CreateSession;
  /** Called after a successful Save so the parent page can keep its
   *  local mirror in sync with the persisted savedId. */
  onSavedIdChange: (savedId: number) => void;
}

/**
 * The post-Generate view: header bar with Back-to-form + Save + Publish
 * + Translate; the generated content panel below. Used by
 * /create/output. Extracted so the route page stays thin.
 *
 * Notable contract: this component owns the per-page side state
 * (translate panel open/closed, viewing-saved cleared, etc.) but
 * persists every meaningful change back to sessionStorage so a refresh
 * or back+forward stays consistent.
 */
export function SingleOutputView({ session, onSavedIdChange }: Props) {
  const { t } = useT();

  // result is guaranteed by the route guard, but null-check anyway.
  const result = session.result!;
  const form = session.form;

  const [savedId, setSavedIdLocal] = useState<number | null>(session.savedId);
  const [viewingSaved, setViewingSaved] = useState<SavedGeneration | null>(
    session.viewingSaved,
  );
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [publishOpen, setPublishOpen] = useState(false);

  const [translateOpen, setTranslateOpen] = useState(false);
  const [translateDefaultLang, setTranslateDefaultLang] = useState("ru");
  const [localTranslations, setLocalTranslations] = useState<
    Record<string, CellTranslation>
  >(session.localTranslations ?? {});

  useEffect(() => {
    let ignored = false;
    getBrainPrompts()
      .then((b) => {
        if (!ignored) {
          setTranslateDefaultLang(
            (b.translate.default_target_language || "ru").toLowerCase(),
          );
        }
      })
      .catch(() => {
        /* keep 'ru' fallback */
      });
    return () => {
      ignored = true;
    };
  }, []);

  async function onSave() {
    if (!result || form.selectedPromptId == null) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await saveGeneration({
        prompt_id: form.selectedPromptId,
        prompt_version_number: form.selectedPromptVersionNumber,
        rendered_prompt: result.rendered_prompt,
        output: result.text,
        variables: form.varValues,
        provider_code: result.provider_used,
        model_used: result.model_used,
        finish_reason: result.finish_reason ?? null,
      });
      setSavedIdLocal(saved.id);
      onSavedIdChange(saved.id);
      // Persist so a refresh after save shows the "Saved" pill instead
      // of offering Save again on the same content.
      updateSession({ savedId: saved.id });
    } catch (err) {
      console.error("[Output] save failed", err);
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  }

  function clearViewingSaved() {
    setViewingSaved(null);
    updateSession({ viewingSaved: null });
  }

  const title = viewingSaved ? viewingSaved.name : t("single.generatedContent");

  return (
    <div className="space-y-4">
      {/* Top bar: back-to-form on the left, primary actions on the
       *  right. Sticky-ish layout keeps the user oriented when the
       *  output panel itself is long. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/create"
          className="inline-flex items-center gap-1 rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          data-testid="output-back-to-form"
        >
          <span aria-hidden="true">←</span> {t("single.backToForm")}
        </Link>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setPublishOpen(true)}
            className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("single.publishTo")}
          </button>
          {result.text.trim().length > 0 && !translateOpen && (
            <button
              type="button"
              onClick={() => setTranslateOpen(true)}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              data-testid="single-translate-toggle"
            >
              {t("translate.button")}
            </button>
          )}
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
              {saving
                ? t("common.saving")
                : savedId != null
                  ? t("single.alreadySaved")
                  : t("common.save")}
            </button>
          )}
        </div>
      </div>

      {viewingSaved && (
        <>
          <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200">
            {t("single.viewingSaved")} <b>{viewingSaved.name}</b>
            <button
              type="button"
              onClick={clearViewingSaved}
              className="ml-3 underline"
            >
              {t("single.clear")}
            </button>
          </div>
          <PublishedToHistory generationId={viewingSaved.id} />
        </>
      )}

      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {t("single.generatedWith", {
          provider: result.provider_used,
          model: result.model_used,
        })}
        {result.finish_reason && ` · ${result.finish_reason}`}
      </p>

      {saveError != null && (
        <ErrorPanel title={t("single.saveFailed")} error={saveError} />
      )}

      {translateOpen ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <div className="mb-2 flex min-h-[40px] items-center">
              <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t("translate.original")}
              </p>
            </div>
            <HtmlViewer content={result.text} title="" height="h-[32rem]" />
          </div>
          <TranslationPanel
            initialTranslations={
              viewingSaved?.translations ?? localTranslations
            }
            defaultTargetLanguage={translateDefaultLang}
            autoRunOnOpen
            onClose={() => setTranslateOpen(false)}
            height="h-[32rem]"
            onTranslate={async (lang, force) => {
              if (viewingSaved) {
                const res = await translateGeneration(
                  viewingSaved.id,
                  lang,
                  force,
                );
                return {
                  text: res.text,
                  provider_used: res.provider_used,
                  model_used: res.model_used,
                  translated_at: res.translated_at,
                };
              }
              if (savedId != null) {
                const res = await translateGeneration(savedId, lang, force);
                return {
                  text: res.text,
                  provider_used: res.provider_used,
                  model_used: res.model_used,
                  translated_at: res.translated_at,
                };
              }
              const res = await translateRawText(result.text, lang);
              return {
                text: res.text,
                provider_used: res.provider_used,
                model_used: res.model_used,
                translated_at: res.translated_at,
              };
            }}
            onTranslated={(lang, entry) => {
              if (viewingSaved) {
                const next = {
                  ...viewingSaved,
                  translations: {
                    ...(viewingSaved.translations ?? {}),
                    [lang]: entry,
                  },
                };
                setViewingSaved(next);
                updateSession({ viewingSaved: next });
              } else {
                setLocalTranslations((prev) => {
                  const merged = { ...prev, [lang]: entry };
                  updateSession({ localTranslations: merged });
                  return merged;
                });
              }
            }}
          />
        </div>
      ) : (
        <HtmlViewer content={result.text} title={title} height="h-[32rem]" />
      )}

      {publishOpen && (
        <PublishToDomainModal
          initialTitle={form.selectedPromptName ?? undefined}
          initialContent={result.text}
          sourceRef={
            savedId != null
              ? { generation_id: savedId, prompt_id: form.selectedPromptId }
              : { prompt_id: form.selectedPromptId }
          }
          onClose={() => setPublishOpen(false)}
        />
      )}
    </div>
  );
}

export { clearSession };
