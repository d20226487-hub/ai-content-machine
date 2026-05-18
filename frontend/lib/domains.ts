import { api, getToken } from "@/lib/api";

export type CmsType = "wordpress" | "custom";
export type AuthType =
  | "wp_app_password"
  | "bearer"
  | "api_key_header"
  | "basic_auth";
export type MultilingualPlugin = "none" | "polylang" | "wpml";

export interface CustomConfig {
  endpoint_path: string;
  body_template: Record<string, unknown>;
  response_id_path: string | null;
  response_url_path: string | null;
  test_endpoint_path: string | null;
}

export type WpFieldType = "text" | "textarea" | "select" | "taxonomy_ids" | "media_url";

export interface WpField {
  key: string;
  label: string;
  type: WpFieldType;
  required?: boolean;
  options?: string[] | null;
  is_meta?: boolean;
  meta_key?: string | null;
  taxonomy?: string | null;
}

export interface PublishProfile {
  name: string;
  post_type: string;
  fields: WpField[];
}

export interface PublishConfig {
  profiles: PublishProfile[];
}

export const DEFAULT_WP_FIELDS: WpField[] = [
  { key: "title", label: "Title", type: "text", required: true },
  { key: "content", label: "Content", type: "textarea", required: true },
  { key: "slug", label: "Slug", type: "text" },
  { key: "status", label: "Status", type: "select", options: ["publish", "draft", "private"], required: true },
  { key: "categories", label: "Categories (IDs)", type: "taxonomy_ids", taxonomy: "categories" },
  { key: "tags", label: "Tags (IDs)", type: "taxonomy_ids", taxonomy: "tags" },
  { key: "featured_media", label: "Featured media", type: "media_url" },
];

export interface Domain {
  id: number;
  name: string;
  base_url: string;
  cms_type: CmsType;
  auth_type: AuthType;
  has_credentials: boolean;
  languages: string[];
  multilingual_plugin: MultilingualPlugin;
  custom_config: CustomConfig | null;
  publish_config: PublishConfig | null;
  // Rate-limit overrides — null means "use global default"
  requests_per_minute: number | null;
  max_concurrency: number | null;
  inter_request_delay_ms: number | null;
  retry_max_attempts: number | null;
  backoff_base_ms: number | null;
  backoff_jitter_ms: number | null;
  respect_retry_after: boolean | null;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  /** Non-null only on rows returned from /domains/trash. */
  deleted_at?: string | null;
}

export interface DomainCreatePayload {
  name: string;
  base_url: string;
  cms_type: CmsType;
  auth_type: AuthType;
  credentials?: string | null;
  languages: string[];
  multilingual_plugin: MultilingualPlugin;
  custom_config?: CustomConfig | null;
  publish_config?: PublishConfig | null;
  requests_per_minute?: number | null;
  max_concurrency?: number | null;
  inter_request_delay_ms?: number | null;
  retry_max_attempts?: number | null;
  backoff_base_ms?: number | null;
  backoff_jitter_ms?: number | null;
  respect_retry_after?: boolean | null;
}

export interface DomainUpdatePayload extends Partial<DomainCreatePayload> {}

export interface TestConnectionResult {
  ok: boolean;
  status_code: number | null;
  detail: string;
  elapsed_ms: number | null;
}

export interface CsvImportResult {
  inserted: number;
  skipped: number;
  errors: { row: number; detail: string }[];
}

export function listDomains() {
  return api<Domain[]>("/domains");
}

export function createDomain(payload: DomainCreatePayload) {
  return api<Domain>("/domains", { method: "POST", body: payload });
}

export function updateDomain(id: number, payload: DomainUpdatePayload) {
  return api<Domain>(`/domains/${id}`, { method: "PATCH", body: payload });
}

/** Soft-delete (move to trash). 409 if an in-flight bulk publish run targets this domain. */
export function deleteDomain(id: number) {
  return api<void>(`/domains/${id}`, { method: "DELETE" });
}

export function testDomain(id: number) {
  return api<TestConnectionResult>(`/domains/${id}/test`, { method: "POST" });
}

// ----- Trash -----

export function listDomainTrash() {
  return api<Domain[]>("/domains/trash");
}

export function getDomainTrashCount() {
  return api<{ count: number }>("/domains/trash/count");
}

export function previewTrashedDomain(id: number) {
  return api<Domain>(`/domains/trash/${id}`);
}

export function restoreDomain(id: number) {
  return api<Domain>(`/domains/${id}/restore`, { method: "POST" });
}

export function permanentlyDeleteDomain(id: number) {
  return api<void>(`/domains/${id}/permanent`, { method: "DELETE" });
}

export function emptyDomainTrash() {
  return api<{ deleted: number }>("/domains/trash", { method: "DELETE" });
}

export function bulkRestoreDomains(ids: number[]) {
  return api<{ restored: number }>("/domains/trash/bulk-restore", {
    method: "POST",
    body: { ids },
  });
}

export function bulkPermanentlyDeleteDomains(ids: number[]) {
  return api<{ deleted: number }>("/domains/trash/bulk", {
    method: "DELETE",
    body: { ids },
  });
}

export interface TrashRetention {
  days: number;
  default: number;
  max: number;
}

export function getDomainTrashRetention() {
  return api<TrashRetention>("/domains/trash/retention");
}

export function setDomainTrashRetention(days: number) {
  return api<TrashRetention>("/domains/trash/retention", {
    method: "PUT",
    body: { days },
  });
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface WpTypeInfo {
  slug: string;
  name: string;
}

export function listWpTypes(domainId: number) {
  return api<WpTypeInfo[]>(`/domains/${domainId}/wp-types`);
}

export function listWpTaxonomies(domainId: number) {
  return api<WpTypeInfo[]>(`/domains/${domainId}/wp-taxonomies`);
}

export function clearMediaCache(domainId: number) {
  return api<{ deleted: number }>(`/domains/${domainId}/media-cache`, {
    method: "DELETE",
  });
}

export function getMediaCacheCount(domainId: number) {
  return api<{ count: number }>(`/domains/${domainId}/media-cache/count`);
}

export async function importDomainsCsv(file: File): Promise<CsvImportResult> {
  const fd = new FormData();
  fd.append("file", file);
  const token = getToken();
  const res = await fetch(`${API_URL}/domains/import-csv`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Import failed (${res.status})`);
  }
  return (await res.json()) as CsvImportResult;
}

/** Bulk-create domains from a JSON array. Same payload shape as POST /domains
 *  per element. Unlike the CSV path this carries the full nested
 *  `publish_config` (profiles + their fields[]) and `custom_config`. */
export function importDomainsJson(
  payloads: DomainCreatePayload[],
): Promise<CsvImportResult> {
  return api<CsvImportResult>("/domains/import-json", {
    method: "POST",
    body: payloads,
  });
}
