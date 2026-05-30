/**
 * Shared state for the /create flow, persisted in sessionStorage so the
 * dedicated /create/output page and the /create form page can hand the
 * baton back and forth without a global store.
 *
 * Why sessionStorage instead of a React context provider? The output
 * page is a separate route — at the moment of navigation the form
 * component unmounts and its state evaporates. Wrapping the entire app
 * in a provider just for the create flow would add reach for unrelated
 * routes. sessionStorage is per-tab, dies with the tab, and survives an
 * F5 reload of either route — which matches the "this work in
 * progress lives until you finish or close the tab" mental model.
 *
 * Why not localStorage? Cross-tab pollution. Two tabs each generating
 * a different prompt would clobber each other's state.
 */
import type {
  CellTranslation,
  GenerateSingleResponse,
  SavedGeneration,
} from "./types";

const STORAGE_KEY = "acm_create_session_v1";

/**
 * Snapshot of the form fields the user filled in to produce the
 * current result. Used by /create/output → Save (it needs prompt_id +
 * variables to call the save endpoint) and by /create on remount to
 * restore what the user was working on.
 */
export interface CreateFormSnapshot {
  /** Prompt the user picked. `null` is the empty form state. */
  selectedPromptId: number | null;
  /** Version that was active at generate time — pinned so a later
   *  prompt edit doesn't silently shift what "this output" came from. */
  selectedPromptVersionNumber: number | null;
  /** Display name snapshot — used by the saved-banner and the default
   *  save name without re-fetching the prompt. */
  selectedPromptName: string | null;
  /** Variables filled in at generate time. Used for save + restore. */
  varValues: Record<string, string>;
  /** Provider + model the user picked. Drives the form's prefill on
   *  restore. The actual generation also records what the provider
   *  reported it used, which can differ (e.g. fallback model). */
  providerCode: string | null;
  model: string | null;
}

/**
 * Full session blob: form snapshot + the result the form produced, plus
 * whatever side state the output page accumulated (translations cache,
 * savedId from Save, viewingSaved metadata when loaded from history).
 */
export interface CreateSession {
  form: CreateFormSnapshot;
  /** The generation result. Null means "no output yet" — used during
   *  form-only restore (user hit Back to form without saving). */
  result: GenerateSingleResponse | null;
  /** Once Save fires, the new Generation id lands here so a re-open of
   *  the output page knows to fetch persistent translations instead of
   *  the local cache. */
  savedId: number | null;
  /** Set when the user opened a saved generation from history rather
   *  than generating fresh. Drives the "Viewing saved: …" banner and
   *  the read-only (no re-save) treatment. */
  viewingSaved: SavedGeneration | null;
  /** In-memory translations cache for the unsaved-result flow — once
   *  savedId is set, fresh fetches go via /generations/{id} translations
   *  field instead. Kept around so re-opening the output page mid-session
   *  doesn't lose what the user already translated. */
  localTranslations: Record<string, CellTranslation>;
}

export function readSession(): CreateSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CreateSession;
    // Minimal shape sanity check — guards against the rare case where
    // a future format change leaves a stale blob in a long-lived tab.
    if (!parsed || typeof parsed !== "object" || !parsed.form) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeSession(state: CreateSession): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* sessionStorage quota / disabled — fail open; the user just loses
     *  the cross-page state, which is no worse than today. */
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Patch helper — read, merge, write. Returns the merged state for
 *  callers that want to also feed it into local React state in the
 *  same render. */
export function updateSession(
  patch: Partial<CreateSession>,
): CreateSession | null {
  const current = readSession();
  if (!current) {
    // If patch.result is provided without a base, accept the patch as a
    // standalone session — the form snapshot has to be present though.
    if (!patch.form) return null;
    const seed: CreateSession = {
      form: patch.form,
      result: patch.result ?? null,
      savedId: patch.savedId ?? null,
      viewingSaved: patch.viewingSaved ?? null,
      localTranslations: patch.localTranslations ?? {},
    };
    writeSession(seed);
    return seed;
  }
  const next: CreateSession = {
    ...current,
    ...patch,
    form: patch.form ?? current.form,
    localTranslations:
      patch.localTranslations ?? current.localTranslations ?? {},
  };
  writeSession(next);
  return next;
}
