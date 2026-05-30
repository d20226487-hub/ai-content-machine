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
  /** Memoized brain-translate results keyed by lowercase language tag.
   *  Absent when no translation has ever been requested for this cell.
   *  Cleared server-side whenever `value` changes. */
  translations?: Record<string, CellTranslation> | null;
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
  columns: BulkColumn[];
  rows: BulkRow[];
  cells: BulkCell[];
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
