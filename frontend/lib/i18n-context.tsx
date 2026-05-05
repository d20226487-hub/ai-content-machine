"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { en } from "@/lib/translations/en";
import { ru } from "@/lib/translations/ru";

export type Lang = "en" | "ru";

const STORAGE_KEY = "acm_lang";

export type TranslationKey = keyof typeof en;
type Dict = Record<TranslationKey, string>;

const DICTS: Record<Lang, Dict> = { en, ru };

interface LangContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const LangContext = createContext<LangContextValue | null>(null);

function format(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (m, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m,
  );
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "ru") setLangState(stored);
  }, []);

  const setLang = useCallback((l: Lang) => {
    localStorage.setItem(STORAGE_KEY, l);
    setLangState(l);
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => {
      const dict = DICTS[lang];
      const fallback = DICTS.en;
      const template = (dict[key] as string | undefined) ?? (fallback[key] as string | undefined) ?? String(key);
      return format(template, vars);
    },
    [lang],
  );

  const value = useMemo<LangContextValue>(
    () => ({ lang, setLang, t }),
    [lang, setLang, t],
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useT() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useT must be used inside <LanguageProvider>");
  return ctx;
}

/**
 * Inline script injected into <head> to set <html lang> before first paint.
 * Avoids a hydration mismatch warning when the user previously chose Russian.
 */
export const langInitScript = `
(function() {
  try {
    var l = localStorage.getItem('${STORAGE_KEY}');
    if (l === 'en' || l === 'ru') document.documentElement.setAttribute('lang', l);
  } catch (_) {}
})();
`;
