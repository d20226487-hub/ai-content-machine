/**
 * Per-user translation language preference.
 *
 * Stored in localStorage (per browser) — matches how other UI prefs
 * already work (theme, page size, etc.). Persisted on each successful
 * translation so the language the user just used becomes the default
 * for the next one-click translate.
 *
 * Resolution order when reading:
 *   1. The stored value in localStorage (set after a successful run).
 *   2. The brain `default_target_language` config (admin-set fallback).
 *   3. Hardcoded `"ru"` so the picker is never empty.
 */
const STORAGE_KEY = "acm_translate_lang";

export function readTranslateLang(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (!v) return null;
    const norm = v.trim().toLowerCase();
    return norm || null;
  } catch {
    return null;
  }
}

export function writeTranslateLang(lang: string): void {
  if (typeof window === "undefined") return;
  const norm = lang.trim().toLowerCase();
  if (!norm) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, norm);
  } catch {
    /* localStorage disabled / full — fail open */
  }
}

/** Resolve "what language should the next translate run target?" by
 *  walking the fallback chain. Pure function — safe to call during
 *  render. */
export function resolveTranslateLang(brainDefault: string | null): string {
  const stored = readTranslateLang();
  if (stored) return stored;
  if (brainDefault) {
    const norm = brainDefault.trim().toLowerCase();
    if (norm) return norm;
  }
  return "ru";
}
