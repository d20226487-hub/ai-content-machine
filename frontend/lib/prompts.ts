import { api } from "./api";
import type {
  Category,
  PromptDetail,
  PromptDraftResponse,
  PromptListItem,
  Tag,
} from "./types";

// ---- Categories ----

export function listCategories(
  opts: { with_counts?: boolean } = {},
): Promise<Category[]> {
  const qs = opts.with_counts ? "?with_counts=true" : "";
  return api<Category[]>(`/categories${qs}`);
}

export function createCategory(
  name: string,
  parent_id: number | null,
): Promise<Category> {
  return api<Category>("/categories", {
    method: "POST",
    body: { name, parent_id },
  });
}

export function renameCategory(id: number, name: string): Promise<Category> {
  return api<Category>(`/categories/${id}`, {
    method: "PATCH",
    body: { name },
  });
}

export function deleteCategory(id: number): Promise<void> {
  return api<void>(`/categories/${id}`, { method: "DELETE" });
}

// ---- Tags ----

export function listTags(): Promise<Tag[]> {
  return api<Tag[]>("/tags");
}

export function createTag(name: string): Promise<Tag> {
  return api<Tag>("/tags", { method: "POST", body: { name } });
}

export function deleteTag(id: number): Promise<void> {
  return api<void>(`/tags/${id}`, { method: "DELETE" });
}

export function renameTag(id: number, name: string): Promise<Tag> {
  return api<Tag>(`/tags/${id}`, { method: "PATCH", body: { name } });
}

export function mergeTag(srcId: number, targetId: number): Promise<Tag> {
  return api<Tag>(`/tags/${srcId}/merge`, {
    method: "POST",
    body: { target_id: targetId },
  });
}

export interface TagWithStats {
  id: number;
  name: string;
  prompt_count: number;
  last_used: string | null;
  created_at: string;
}

export interface TagListResponse {
  items: TagWithStats[];
  total: number;
  page: number;
  page_size: number;
}

export function listTagsManage(opts: {
  page?: number;
  page_size?: number;
  q?: string;
} = {}): Promise<TagListResponse> {
  const sp = new URLSearchParams();
  if (opts.page) sp.set("page", String(opts.page));
  if (opts.page_size) sp.set("page_size", String(opts.page_size));
  if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
  const qs = sp.toString();
  return api<TagListResponse>(`/tags/manage${qs ? "?" + qs : ""}`);
}

// ---- Prompts ----

interface ListFilters {
  category_id?: number | null;
  include_descendants?: boolean;
  /** AND semantics — a prompt must carry every requested tag to match. */
  tag_ids?: number[];
  q?: string;
  page?: number;
  page_size?: number;
}

export interface PromptListResponse {
  items: PromptListItem[];
  total: number;
  page: number;
  page_size: number;
}

export function listPrompts(filters: ListFilters = {}): Promise<PromptListResponse> {
  const sp = new URLSearchParams();
  if (filters.category_id != null) sp.set("category_id", String(filters.category_id));
  if (filters.include_descendants) sp.set("include_descendants", "true");
  if (filters.tag_ids && filters.tag_ids.length > 0) {
    for (const tid of filters.tag_ids) sp.append("tag_ids", String(tid));
  }
  if (filters.q && filters.q.trim()) sp.set("q", filters.q.trim());
  if (filters.page) sp.set("page", String(filters.page));
  if (filters.page_size) sp.set("page_size", String(filters.page_size));
  const qs = sp.toString();
  return api<PromptListResponse>(`/prompts${qs ? "?" + qs : ""}`);
}

export function getPrompt(id: number): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}`);
}

export function getPromptVersion(
  id: number,
  versionNumber: number,
): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}/versions/${versionNumber}`);
}

export interface CreatePromptPayload {
  name: string;
  category_id: number | null;
  content: string;
  change_note?: string | null;
  tag_ids?: number[];
}

export function createPrompt(payload: CreatePromptPayload): Promise<PromptDetail> {
  return api<PromptDetail>("/prompts", { method: "POST", body: payload });
}

export interface UpdatePromptMetaPayload {
  name?: string;
  category_id?: number | null;
  tag_ids?: number[];
}

export function updatePromptMeta(
  id: number,
  patch: UpdatePromptMetaPayload,
): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}`, { method: "PATCH", body: patch });
}

export function createPromptVersion(
  id: number,
  content: string,
  change_note?: string | null,
): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}/versions`, {
    method: "POST",
    body: { content, change_note: change_note ?? null },
  });
}

/** Edit just the change_note on an existing version (no new version created). */
export function editVersionNote(
  id: number,
  version_number: number,
  change_note: string | null,
): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}/versions/${version_number}/note`, {
    method: "PATCH",
    body: { change_note },
  });
}

export function revertPrompt(
  id: number,
  target_version_number: number,
  change_note?: string | null,
): Promise<PromptDetail> {
  return api<PromptDetail>(`/prompts/${id}/revert`, {
    method: "POST",
    body: { target_version_number, change_note: change_note ?? null },
  });
}

export function deletePrompt(id: number): Promise<void> {
  return api<void>(`/prompts/${id}`, { method: "DELETE" });
}

// ---- AI assist ----

export function draftPromptWithAI(
  description: string,
  provider_code?: string,
  model?: string,
): Promise<PromptDraftResponse> {
  return api<PromptDraftResponse>("/prompts/draft", {
    method: "POST",
    body: { description, provider_code: provider_code ?? null, model: model ?? null },
  });
}
