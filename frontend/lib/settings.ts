import { api } from "./api";
import type { ConnectionTestResult, Provider, ProviderUpdate } from "./types";

export function listProviders(): Promise<Provider[]> {
  return api<Provider[]>("/settings/providers");
}

export function updateProvider(
  code: string,
  patch: ProviderUpdate,
): Promise<Provider> {
  return api<Provider>(`/settings/providers/${code}`, {
    method: "PATCH",
    body: patch,
  });
}

export interface TestConnectionPayload {
  /** If provided, test this key. Otherwise the stored key is decrypted and used. */
  api_key?: string;
  model?: string;
}

export function testProviderConnection(
  code: string,
  payload: TestConnectionPayload = {},
): Promise<ConnectionTestResult> {
  return api<ConnectionTestResult>(`/settings/providers/${code}/test`, {
    method: "POST",
    body: payload,
  });
}

/**
 * Global generation limits (Settings → Generation).
 *
 * `max_output_tokens` is the ceiling every bulk cell inherits unless its
 * column overrides it — the old behaviour was a hardcoded 2048, which
 * truncated long-form output around 5.7k characters.
 *
 * `thinking_budget` covers models that bill reasoning against that same
 * ceiling (Gemini 2.5, Claude Sonnet 5): null sends nothing and keeps the
 * model default, 0 disables thinking so the whole budget goes to the answer.
 */
export interface GenerationDefaults {
  max_output_tokens: number;
  thinking_budget: number | null;
}

export function getGenerationDefaults() {
  return api<GenerationDefaults>("/settings/generation");
}

export function setGenerationDefaults(payload: GenerationDefaults) {
  return api<GenerationDefaults>("/settings/generation", {
    method: "PUT",
    body: payload,
  });
}
