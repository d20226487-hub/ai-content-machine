import { api } from "./api";
import type {
  EnabledProvider,
  GenerateSingleResponse,
  RenderPromptResponse,
  SavedGeneration,
  SavedGenerationListResponse,
} from "./types";

export function listEnabledProviders(): Promise<EnabledProvider[]> {
  return api<EnabledProvider[]>("/generate/providers");
}

export interface RenderPromptPayload {
  prompt_id: number;
  version_number?: number | null;
  variables: Record<string, string>;
}

export function renderPrompt(p: RenderPromptPayload): Promise<RenderPromptResponse> {
  return api<RenderPromptResponse>("/generate/render", {
    method: "POST",
    body: {
      prompt_id: p.prompt_id,
      version_number: p.version_number ?? null,
      variables: p.variables,
    },
  });
}

export interface GenerateSinglePayload {
  prompt_id: number;
  version_number?: number | null;
  variables: Record<string, string>;
  provider_code?: string | null;
  model?: string | null;
  temperature?: number | null;
  max_output_tokens?: number | null;
}

export function generateSingle(
  p: GenerateSinglePayload,
): Promise<GenerateSingleResponse> {
  return api<GenerateSingleResponse>("/generate/single", {
    method: "POST",
    body: {
      prompt_id: p.prompt_id,
      version_number: p.version_number ?? null,
      variables: p.variables,
      provider_code: p.provider_code ?? null,
      model: p.model ?? null,
      temperature: p.temperature ?? null,
      max_output_tokens: p.max_output_tokens ?? null,
    },
  });
}

// ----- Saved generations -----

export interface SaveGenerationPayload {
  name?: string;
  prompt_id: number;
  prompt_version_number?: number | null;
  rendered_prompt: string;
  output: string;
  variables: Record<string, string>;
  provider_code: string;
  model_used: string;
  finish_reason?: string | null;
}

export function saveGeneration(p: SaveGenerationPayload): Promise<SavedGeneration> {
  return api<SavedGeneration>("/generations", { method: "POST", body: p });
}

export function listSavedGenerations(
  opts: { page?: number; pageSize?: number; q?: string } = {},
): Promise<SavedGenerationListResponse> {
  const sp = new URLSearchParams();
  if (opts.page) sp.set("page", String(opts.page));
  if (opts.pageSize) sp.set("page_size", String(opts.pageSize));
  if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
  const qs = sp.toString();
  return api<SavedGenerationListResponse>(
    `/generations${qs ? `?${qs}` : ""}`,
  );
}

export function getSavedGeneration(id: number): Promise<SavedGeneration> {
  return api<SavedGeneration>(`/generations/${id}`);
}

export function renameSavedGeneration(id: number, name: string): Promise<SavedGeneration> {
  return api<SavedGeneration>(`/generations/${id}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteSavedGeneration(id: number): Promise<void> {
  return api<void>(`/generations/${id}`, { method: "DELETE" });
}
