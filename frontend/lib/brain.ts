import { api } from "./api";
import type { CellTranslation } from "./types";

export interface TranslatePromptConfig {
  prompt: string;
  provider_code: string | null;
  model: string | null;
  default_target_language: string;
}

export interface FixLinksPromptConfig {
  prompt: string;
  provider_code: string | null;
  model: string | null;
}

export interface BrainPrompts {
  translate: TranslatePromptConfig;
  fix_links: FixLinksPromptConfig;
}

export function getBrainPrompts(): Promise<BrainPrompts> {
  return api<BrainPrompts>("/brain/prompts");
}

export function updateTranslateConfig(
  payload: TranslatePromptConfig,
): Promise<TranslatePromptConfig> {
  return api<TranslatePromptConfig>("/brain/prompts/translate", {
    method: "PUT",
    body: payload,
  });
}

export function updateFixLinksConfig(
  payload: FixLinksPromptConfig,
): Promise<FixLinksPromptConfig> {
  return api<FixLinksPromptConfig>("/brain/prompts/fix-links", {
    method: "PUT",
    body: payload,
  });
}

export interface TranslateCellResponse extends CellTranslation {
  target_language: string;
  cached: boolean;
}

export function translateCell(
  tableId: number,
  rowId: number,
  columnId: number,
  targetLanguage: string,
  /** Set to true to bypass the server-side per-cell translation cache
   *  and force a fresh LLM call. Used by the Re-translate button. */
  force = false,
): Promise<TranslateCellResponse> {
  return api<TranslateCellResponse>(
    `/library/tables/${tableId}/cells/${rowId}/${columnId}/translate`,
    {
      method: "POST",
      body: { target_language: targetLanguage, force },
    },
  );
}

/** Translate a saved single-mode generation. Memoized server-side on
 *  ``generations.translations`` so opening the same saved generation
 *  later is free. */
export function translateGeneration(
  generationId: number,
  targetLanguage: string,
  force = false,
): Promise<TranslateCellResponse> {
  return api<TranslateCellResponse>(
    `/generations/${generationId}/translate`,
    {
      method: "POST",
      body: { target_language: targetLanguage, force },
    },
  );
}

/** Translate a prompt version's template content. Memoized server-side
 *  on ``prompt_versions.translations``; versions are immutable so the
 *  cache is permanent once written. */
export function translatePromptVersion(
  promptId: number,
  versionNumber: number,
  targetLanguage: string,
  force = false,
): Promise<TranslateCellResponse> {
  return api<TranslateCellResponse>(
    `/prompts/${promptId}/versions/${versionNumber}/translate`,
    {
      method: "POST",
      body: { target_language: targetLanguage, force },
    },
  );
}

/** Translate arbitrary text — used by ephemeral surfaces (test-prompt
 *  modal, unsaved single drafts). No memoization; every call hits the
 *  LLM. */
export function translateRawText(
  text: string,
  targetLanguage: string,
): Promise<TranslateCellResponse> {
  return api<TranslateCellResponse>("/brain/translate-text", {
    method: "POST",
    body: { text, target_language: targetLanguage },
  });
}
