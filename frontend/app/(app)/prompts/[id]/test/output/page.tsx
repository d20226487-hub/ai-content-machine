"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { HtmlViewer } from "@/components/HtmlViewer";
import { TranslationPanel } from "@/components/TranslationPanel";
import { getBrainPrompts, translateRawText } from "@/lib/brain";
import { useT } from "@/lib/i18n-context";
import {
  readTestSession,
  type TestSession,
  updateTestSession,
} from "@/lib/testSession";
import type { CellTranslation } from "@/lib/types";

/**
 * Output view for a prompt-test run. No Save, no Publish — just the
 * generated content, a Back-to-form button, and an optional Translate
 * panel. Translations are stateless (translateRawText) and cached in
 * sessionStorage alongside the result for the lifetime of the tab.
 *
 * Direct visit without a stored result bounces back to the form page
 * for the same prompt id, so a bookmarked link is harmless.
 */
export default function TestOutputPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const promptId = Number(params.id);

  const [session, setSession] = useState<TestSession | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const [translateOpen, setTranslateOpen] = useState(false);
  const [translateDefaultLang, setTranslateDefaultLang] = useState("ru");
  const [localTranslations, setLocalTranslations] = useState<
    Record<string, CellTranslation>
  >({});

  useEffect(() => {
    const s = readTestSession();
    setSession(s);
    setLocalTranslations(s?.localTranslations ?? {});
    setHydrated(true);
    if (!s || !s.result || s.form.promptId !== promptId) {
      // Bookmarked / refreshed without a matching session → bounce to
      // the form. router.replace so /test/output doesn't sit in the
      // back stack as an empty page.
      router.replace(`/prompts/${promptId}/test`);
    }
  }, [promptId, router]);

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

  const title = useMemo(
    () => session?.form.promptName ?? t("test.pageTitle"),
    [session, t],
  );

  if (!hydrated || !session || !session.result) {
    return (
      <main className="mx-auto max-w-6xl p-8">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      </main>
    );
  }

  const result = session.result;

  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-6">
        <h1 className="truncate text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
          {title}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("test.outputSubtitle")}
        </p>
      </header>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            href={`/prompts/${promptId}/test`}
            className="inline-flex items-center gap-1 rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            data-testid="test-back-to-form"
          >
            <span aria-hidden="true">←</span> {t("single.backToForm")}
          </Link>

          {result.text.trim().length > 0 && !translateOpen && (
            <button
              type="button"
              onClick={() => setTranslateOpen(true)}
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              data-testid="test-translate-toggle"
            >
              {t("translate.button")}
            </button>
          )}
        </div>

        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("single.generatedWith", {
            provider: result.provider_used,
            model: result.model_used,
          })}
          {result.finish_reason && ` · ${result.finish_reason}`}
        </p>

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
              initialTranslations={localTranslations}
              defaultTargetLanguage={translateDefaultLang}
              autoRunOnOpen
              onClose={() => setTranslateOpen(false)}
              height="h-[32rem]"
              onTranslate={async (lang) => {
                const res = await translateRawText(result.text, lang);
                return {
                  text: res.text,
                  provider_used: res.provider_used,
                  model_used: res.model_used,
                  translated_at: res.translated_at,
                };
              }}
              onTranslated={(lang, entry) =>
                setLocalTranslations((prev) => {
                  const merged = { ...prev, [lang]: entry };
                  updateTestSession({ localTranslations: merged });
                  return merged;
                })
              }
            />
          </div>
        ) : (
          <HtmlViewer
            content={result.text}
            title={t("single.generatedContent")}
            height="h-[32rem]"
          />
        )}
      </div>
    </main>
  );
}
