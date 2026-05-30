/**
 * Test-prompt session — sibling of createSession but stripped down.
 *
 * Test runs are deliberately ephemeral: no save, no publish, no
 * memoization. The session blob exists only so the two route halves
 * (form page + output page) can hand state across a navigation, and
 * so a F5 on the output page survives. It's per-tab (sessionStorage)
 * and dies with the tab.
 *
 * Why a separate adapter and not a reuse of createSession: the test
 * flow lacks savedId / viewingSaved entirely, and its form snapshot
 * carries a prompt_id from the URL rather than from a user picker.
 * Conflating them would mean either page guarding "is this a test or
 * a create run?" on every state read — easier to keep two slim shapes.
 */
import type { CellTranslation, GenerateSingleResponse } from "./types";

const STORAGE_KEY = "acm_test_session_v1";

export interface TestFormSnapshot {
  promptId: number;
  /** Pinned at generate time so a later prompt edit doesn't shift
   *  what "this output" was produced from. */
  promptVersionNumber: number | null;
  /** Display name for the output-page header. */
  promptName: string;
  varValues: Record<string, string>;
  providerCode: string | null;
  model: string | null;
}

export interface TestSession {
  form: TestFormSnapshot;
  /** The generation result. Null when the user is in form-only state
   *  (e.g. after Back-to-form before a fresh Generate). */
  result: GenerateSingleResponse | null;
  /** In-memory translations cache. Test results don't have an entity
   *  to memoize against server-side, so the cache lives here for the
   *  span of the tab. */
  localTranslations: Record<string, CellTranslation>;
}

export function readTestSession(): TestSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TestSession;
    if (!parsed || !parsed.form) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeTestSession(state: TestSession): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* sessionStorage disabled / full — fail open */
  }
}

export function clearTestSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Patch helper: read, merge, write. Returns the merged blob so the
 *  caller can also feed it into local React state. */
export function updateTestSession(
  patch: Partial<TestSession>,
): TestSession | null {
  const current = readTestSession();
  if (!current) {
    if (!patch.form) return null;
    const seed: TestSession = {
      form: patch.form,
      result: patch.result ?? null,
      localTranslations: patch.localTranslations ?? {},
    };
    writeTestSession(seed);
    return seed;
  }
  const next: TestSession = {
    ...current,
    ...patch,
    form: patch.form ?? current.form,
    localTranslations:
      patch.localTranslations ?? current.localTranslations ?? {},
  };
  writeTestSession(next);
  return next;
}
