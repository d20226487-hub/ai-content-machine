"use client";

import { useEffect, useMemo, useState } from "react";

import { HtmlViewer } from "@/components/HtmlViewer";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  readTranslateLang,
  resolveTranslateLang,
  writeTranslateLang,
} from "@/lib/translateLangPref";
import type { CellTranslation } from "@/lib/types";

/**
 * Reusable side-by-side translation panel.
 *
 * Layout:
 *   [TRANSLATION ×]                                         ← clean header
 *   ┌─────────────────────────────┐
 *   │                             │
 *   │  HtmlViewer (translation)   │
 *   │                             │
 *   └─────────────────────────────┘
 *   [provider · model · time]   [lang select] [Translate]   ← footer
 *
 * The previous layout crammed the language picker, custom-code input,
 * close X, and Re-translate button all into the header row next to the
 * HtmlViewer's own 4-button toolbar — visually noisy and hard to scan.
 * The footer row places the action controls next to the meta line and
 * leaves the header for the label + close only.
 */
export interface TranslationPanelProps {
  initialTranslations: Record<string, CellTranslation> | null;
  defaultTargetLanguage: string;
  onTranslate: (lang: string, force: boolean) => Promise<CellTranslation>;
  onTranslated?: (lang: string, entry: CellTranslation) => void;
  onClose?: () => void;
  /** Fixed iframe height — defaults to h-[28rem] so the panel can sit
   *  next to a same-height original pane. */
  height?: string;
  hideClose?: boolean;
  /** Forward to the inner HtmlViewer. When true, the toolbar shrinks
   *  to just Copy — useful for prompt-template translations where the
   *  content is plain text and the full toolbar is visual noise. */
  compact?: boolean;
  /** When true, fire a translate call as soon as the panel mounts so
   *  clicking the surface-level Translate button feels like a single
   *  action rather than "open panel, then press button". Skipped when a
   *  cached entry for the resolved language is already present — no
   *  point re-billing the LLM for what's already on screen. */
  autoRunOnOpen?: boolean;
}

const COMMON_LANGS: { code: string; label: string }[] = [
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
  { code: "uk", label: "Українська" },
  { code: "pl", label: "Polski" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "it", label: "Italiano" },
  { code: "pt", label: "Português" },
  { code: "tr", label: "Türkçe" },
  { code: "zh", label: "中文" },
];

const CUSTOM_SENTINEL = "__custom__";

export function TranslationPanel({
  initialTranslations,
  defaultTargetLanguage,
  onTranslate,
  onTranslated,
  onClose,
  height = "h-[28rem]",
  hideClose = false,
  compact = false,
  autoRunOnOpen = false,
}: TranslationPanelProps) {
  const { t } = useT();

  // Initial language resolution:
  //   1. The user's per-browser preference in localStorage (set on each
  //      successful run, so it tracks "the language I just used").
  //   2. The first existing translation entry — if the cell has a
  //      cached translation, default to showing that one so the user
  //      doesn't pay for a fresh call to reproduce it.
  //   3. The brain default_target_language admin config.
  //   4. Hardcoded "ru".
  const initialLang = useMemo(() => {
    const stored = readTranslateLang();
    if (stored) return stored;
    if (initialTranslations) {
      const keys = Object.keys(initialTranslations);
      if (keys.length > 0) return keys[0];
    }
    return resolveTranslateLang(defaultTargetLanguage);
  }, [initialTranslations, defaultTargetLanguage]);

  const [targetLang, setTargetLang] = useState(initialLang);
  // "Custom…" mode swaps the select for a free-text input so the user
  // can type any BCP-47 tag. The select still shows the common list and
  // is one click away — no separate input cluttering the layout by
  // default.
  const [customMode, setCustomMode] = useState(
    !COMMON_LANGS.some((l) => l.code === initialLang),
  );
  const [translations, setTranslations] = useState<
    Record<string, CellTranslation>
  >(initialTranslations ?? {});
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);

  // Re-sync when the parent swaps the underlying entity (e.g. user
  // opens a different saved generation while panel is open).
  useEffect(() => {
    setTranslations(initialTranslations ?? {});
  }, [initialTranslations]);

  const currentTranslation = translations[targetLang] ?? null;

  async function runTranslate() {
    if (translating) return;
    const lang = targetLang.trim().toLowerCase();
    if (!lang) {
      setTranslateError(t("translate.noLang"));
      return;
    }
    setTranslating(true);
    setTranslateError(null);
    try {
      const force = !!translations[lang];
      const entry = await onTranslate(lang, force);
      setTranslations((prev) => ({ ...prev, [lang]: entry }));
      onTranslated?.(lang, entry);
      // Persist the just-used language as the user's new default so
      // the next click of the surface-level Translate button picks the
      // same language without prompting. Only persisted on success —
      // a failed run shouldn't change the default away from what works.
      writeTranslateLang(lang);
    } catch (err) {
      setTranslateError(
        err instanceof ApiError ? err.message : t("common.somethingWentWrong"),
      );
    } finally {
      setTranslating(false);
    }
  }

  // 1-click translate: when the panel is opened with autoRunOnOpen,
  // kick off a translation as soon as we're mounted. Skip when a
  // cached entry for this language already exists (already on screen)
  // or while a run is already in flight (StrictMode double-mount).
  useEffect(() => {
    if (!autoRunOnOpen) return;
    const lang = targetLang.trim().toLowerCase();
    if (!lang) return;
    if (translations[lang]) return; // cache hit — nothing to do
    void runTranslate();
    // We intentionally depend only on the mount sentinel — re-running
    // when translations changes would loop after the entry lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col">
      {/* Header: label + close X on the left, lang picker + Translate
       *  button on the right. Earlier this lived at the footer below
       *  the iframe — clean visually but inconvenient because past a
       *  28–32rem iframe the controls were off-screen and required
       *  scrolling to reach. Top placement keeps them always in
       *  reach. min-h matches the surrounding pane's label row when
       *  used in side-by-side so iframes start at the same Y. */}
      <div className="mb-2 flex min-h-[40px] flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("translate.translation")}
          </p>
          {!hideClose && onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded p-0.5 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
              title={t("translate.closePanel")}
              aria-label={t("translate.closePanel")}
              data-testid="translate-close"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 20 20"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M5 5l10 10M15 5L5 15"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {customMode ? (
            <input
              type="text"
              value={targetLang}
              onChange={(e) =>
                setTargetLang(e.target.value.toLowerCase().trim())
              }
              onBlur={() => {
                if (!targetLang.trim()) setCustomMode(false);
              }}
              autoFocus
              className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              placeholder="ru"
              maxLength={16}
              aria-label={t("translate.langInput")}
            />
          ) : (
            <select
              value={
                COMMON_LANGS.some((l) => l.code === targetLang)
                  ? targetLang
                  : CUSTOM_SENTINEL
              }
              onChange={(e) => {
                const v = e.target.value;
                if (v === CUSTOM_SENTINEL) {
                  setCustomMode(true);
                  return;
                }
                setTargetLang(v);
              }}
              className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              aria-label={t("translate.langSelect")}
            >
              {COMMON_LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label} ({l.code})
                </option>
              ))}
              <option value={CUSTOM_SENTINEL}>
                {t("translate.langCustomOption")}
              </option>
            </select>
          )}
          <button
            type="button"
            onClick={() => void runTranslate()}
            disabled={translating}
            className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            data-testid="translate-run"
          >
            {translating
              ? t("translate.translating")
              : currentTranslation
                ? t("translate.retranslate")
                : t("translate.translate")}
          </button>
        </div>
      </div>

      {translateError && (
        <p className="mb-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {translateError}
        </p>
      )}

      {currentTranslation ? (
        <HtmlViewer
          content={currentTranslation.text}
          title=""
          height={height}
          compact={compact}
        />
      ) : (
        <div
          className={
            "flex items-center justify-center rounded-md border border-dashed border-neutral-300 px-6 text-center text-xs text-neutral-500 dark:border-neutral-700 dark:text-neutral-400 " +
            height
          }
        >
          {translating ? t("translate.translating") : t("translate.emptyHint")}
        </div>
      )}

      {/* Footer: provider / model / timestamp only — purely
       *  informational, no interaction. Stays at the bottom to keep
       *  the busy controls clustered up top. */}
      {currentTranslation && (
        <p className="mt-2 text-[11px] text-neutral-500 dark:text-neutral-400">
          {currentTranslation.provider_used} · {currentTranslation.model_used}
          {currentTranslation.translated_at && (
            <>
              {" · "}
              {new Date(currentTranslation.translated_at).toLocaleString()}
            </>
          )}
        </p>
      )}
    </div>
  );
}
