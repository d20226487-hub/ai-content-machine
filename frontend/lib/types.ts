export type RoleName = "admin" | "manager" | "content_generator" | string;

export interface Role {
  id: number;
  name: RoleName;
  description: string | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  role: Role;
  created_at: string;
  /** Non-null only on rows returned from /users/trash. */
  deleted_at?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserCreatePayload {
  email: string;
  full_name: string | null;
  password: string;
  role_id: number;
  is_active: boolean;
}

export interface UserUpdatePayload {
  full_name?: string | null;
  role_id?: number;
  is_active?: boolean;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
  // Populated when listCategories({ with_counts: true }); null otherwise.
  prompt_count?: number | null;
  subfolder_count?: number | null;
}

export interface Tag {
  id: number;
  name: string;
}

export interface PromptVersionRead {
  id: number;
  version_number: number;
  content: string;
  change_note: string | null;
  created_by_id: number | null;
  created_by_name: string | null;
  created_by_email: string | null;
  created_at: string;
  /** Memoized translations of `content`. Persists per version. */
  translations?: Record<string, CellTranslation> | null;
}

export interface PromptVersionSummary {
  id: number;
  version_number: number;
  change_note: string | null;
  created_by_id: number | null;
  created_by_name: string | null;
  created_by_email: string | null;
  created_at: string;
}

export interface PromptListItem {
  id: number;
  name: string;
  category_id: number | null;
  current_version: PromptVersionRead | null;
  tags: Tag[];
  created_by_id: number | null;
  created_by_name: string | null;
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
  /** Non-null only on rows returned from /prompts/trash. */
  deleted_at?: string | null;
}

export interface PromptDetail {
  id: number;
  name: string;
  category_id: number | null;
  current_version: PromptVersionRead | null;
  versions: PromptVersionSummary[];
  tags: Tag[];
  variables: string[];
  created_by_id: number | null;
  created_by_name: string | null;
  created_by_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptDraftResponse {
  draft_content: string;
  provider_used: string;
  model_used: string;
}

export interface EnabledProvider {
  code: string;
  display_name: string;
  default_model: string | null;
  available_models: string[];
  has_api_key: boolean;
}

export interface GenerateSingleResponse {
  text: string;
  rendered_prompt: string;
  provider_used: string;
  model_used: string;
  finish_reason: string | null;
  missing_variables: string[];
}

export interface RenderPromptResponse {
  rendered_prompt: string;
  expected_variables: string[];
  missing_variables: string[];
}

export interface SavedGenerationListItem {
  id: number;
  name: string;
  prompt_id: number | null;
  prompt_version_number: number | null;
  prompt_name_snapshot: string;
  provider_code: string;
  model_used: string;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface SavedGeneration extends SavedGenerationListItem {
  rendered_prompt: string;
  output: string;
  variables: Record<string, string>;
  finish_reason: string | null;
  /** Memoized translations of `output`. Persists across reloads when
   *  the saved generation is opened again. */
  translations?: Record<string, CellTranslation> | null;
}

export interface SavedGenerationListResponse {
  items: SavedGenerationListItem[];
  total: number;
  page: number;
  page_size: number;
}

// ----- Library / Bulk -----

export type ColumnKind = "input" | "output";
export type CellStatus =
  | "empty"
  | "manual"
  | "generating"
  | "generated"
  | "failed";

export interface BulkColumn {
  id: number;
  position: number;
  name: string;
  kind: ColumnKind;
  prompt_id: number | null;
  prompt_version_number: number | null;
  variable_map: Record<string, number>;
  provider_code: string | null;
  model: string | null;
  /** Output-token ceiling for this column's generations.
   *  Null = inherit the global default from Settings → Generation. */
  max_output_tokens?: number | null;
  /** Grounding source for this column's generations. Null/absent = off.
   *  "google_search" = research the topic with Gemini + Google Search on
   *  Vertex. Only the Vertex Gemini path honours it. */
  grounding?: "google_search" | null;
}

export interface BulkRow {
  id: number;
  position: number;
}

export interface CellTranslation {
  text: string;
  provider_used: string | null;
  model_used: string | null;
  translated_at: string | null;
}

export interface BulkCell {
  id: number;
  row_id: number;
  column_id: number;
  value: string | null;
  status: CellStatus;
  error: string | null;
  model_used: string | null;
  generated_at: string | null;
  updated_at: string;
  /** Raw provider stop reason for the last generation ("STOP" / "MAX_TOKENS" /
   *  "length" / "max_tokens" / "SAFETY" ...). Null for hand-typed cells. */
  finish_reason?: string | null;
  /** Server-derived: the reply hit the output-token ceiling, so `value` is a
   *  partial. Raise the column's or the global max output tokens and retry. */
  truncated?: boolean;
  /** Memoized brain-translate results keyed by lowercase language tag.
   *  Absent when no translation has ever been requested for this cell.
   *  Cleared server-side whenever `value` changes. */
  translations?: Record<string, CellTranslation> | null;
  /** Provenance from a grounded generation: the search queries the model ran
   *  and the web sources it cited. Absent when the cell was never grounded;
   *  cleared server-side whenever `value` changes. Source URIs are Vertex
   *  redirect links that expire (~30 days). */
  grounding_sources?: GroundingSources | null;
}

export interface GroundingSource {
  uri: string;
  title: string;
}

export interface GroundingSources {
  queries: string[];
  sources: GroundingSource[];
  retrieved_at?: string;
}

export interface BulkTableListItem {
  id: number;
  name: string;
  description: string | null;
  folder_id: number | null;
  created_by_id: number | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  column_count: number;
  row_count: number;
  /** Non-null only on rows returned from /library/trash. */
  deleted_at?: string | null;
}

/** One site's planned page list, from a Google-Docs import (table.gdocs_structure). */
export interface GdocsSiteStructure {
  domain: string;
  language: string;
  structure: string[];
}

/** One row's AI slug mapping (table.gdocs_slug_audit) — anchor → final slug. */
export interface GdocsSlugAudit {
  row: number;
  domain: string;
  language: string;
  seo_title: string;
  anchor: string; // raw link anchor the writer attached ("before")
  slug: string; // final slug taken from Structure ("after")
  changed: boolean; // AI/structure slug differs from the anchor's own slug
  unmatched: boolean; // no Structure pairing → no-exact-slug
}

export interface BulkTable {
  id: number;
  name: string;
  description: string | null;
  folder_id: number | null;
  created_by_id: number | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  /** Non-null only when fetched via /library/trash/{id}. */
  deleted_at?: string | null;
  /** Autotool (3rd publishing mode): whether the table is exposed as a
   *  public CSV, and the token forming its URL (null when disabled). */
  autotool_enabled: boolean;
  autotool_token: string | null;
  /** Per-site planned page list for Google-Docs-imported tables (drives the
   *  "Site structure" reference panel). Null for tables not built that way. */
  gdocs_structure: GdocsSiteStructure[] | null;
  /** Per-row AI slug mapping (anchor → final slug) for review. Null otherwise. */
  gdocs_slug_audit: GdocsSlugAudit[] | null;
  columns: BulkColumn[];
  rows: BulkRow[];
  cells: BulkCell[];
  /** Total rows in the table regardless of pagination. On a paginated
   *  fetch, `rows`/`cells` hold only the current page while this reflects
   *  the whole table. On a full fetch it equals rows.length. */
  total_row_count: number;
}

export interface Provider {
  id: number;
  code: string;
  display_name: string;
  enabled: boolean;
  has_api_key: boolean;
  has_extra_config: boolean;
  // Non-secret subset of structured creds (e.g. Vertex AI's project_id +
  // location). Secret fields (service_account_json) are stripped server-
  // side and signalled only via has_extra_config.
  extra_config_public: Record<string, string>;

  default_model: string | null;
  prompt_creation_model: string | null;
  available_models: string[];

  requests_per_minute: number;
  max_concurrency: number;
  batch_size: number;
  inter_request_delay_ms: number;
  retry_max_attempts: number;
  backoff_base_ms: number;
  backoff_jitter_ms: number;
  respect_retry_after: boolean;
}

export interface ConnectionTestResult {
  ok: boolean;
  provider_code: string;
  model_used: string | null;
  latency_ms: number | null;
  error: string | null;
  sample_output: string | null;
}

export type ProviderUpdate = Partial<{
  enabled: boolean;
  api_key: string; // "" clears, omit leaves unchanged, value sets
  // Same per-field semantics as api_key: omit = unchanged, "" = clear,
  // non-empty = overwrite. Send {} to wipe every field.
  extra_config: Record<string, string>;
  default_model: string | null;
  prompt_creation_model: string | null;
  available_models: string[];
  requests_per_minute: number;
  max_concurrency: number;
  batch_size: number;
  inter_request_delay_ms: number;
  retry_max_attempts: number;
  backoff_base_ms: number;
  backoff_jitter_ms: number;
  respect_retry_after: boolean;
}>;
