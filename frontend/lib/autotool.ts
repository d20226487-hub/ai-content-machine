import { api } from "./api";

/** Masked config: the API key is never returned, only whether one is set. */
export interface AutotoolConfig {
  target_url: string | null;
  api_key_configured: boolean;
}

export interface AutotoolConfigUpdate {
  /** omit = unchanged, "" = clear, non-empty = set */
  target_url?: string | null;
  /** omit = unchanged, "" = clear, non-empty = set */
  api_key?: string | null;
}

export interface AutotoolTestResult {
  ok: boolean;
  status_code: number | null;
  detail: string;
  elapsed_ms: number | null;
}

export function getAutotoolConfig(): Promise<AutotoolConfig> {
  return api<AutotoolConfig>("/autotool/config");
}

export function saveAutotoolConfig(
  payload: AutotoolConfigUpdate,
): Promise<AutotoolConfig> {
  return api<AutotoolConfig>("/autotool/config", {
    method: "PUT",
    body: payload,
  });
}

export function testAutotoolConfig(): Promise<AutotoolTestResult> {
  return api<AutotoolTestResult>("/autotool/config/test", { method: "POST" });
}

// ----- shared tables + POST request preview -----

export interface AutotoolTableItem {
  id: number;
  name: string;
  autotool_token: string | null;
  csv_path: string | null;
  row_count: number;
  column_count: number;
  updated_at: string;
}

export interface AutotoolTablesPage {
  items: AutotoolTableItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AutotoolPostPreview {
  method: string;
  url: string | null;
  headers: Record<string, string>;
  body: { sites: string[]; data: { file: string | null } };
  columns: { id: number; name: string }[];
  site_column_id: number | null;
  detected_site_column_id: number | null;
  site_count: number;
  target_configured: boolean;
  api_key_configured: boolean;
}

export function listSharedTables(
  page = 1,
  pageSize = 20,
): Promise<AutotoolTablesPage> {
  return api<AutotoolTablesPage>(
    `/autotool/tables?page=${page}&page_size=${pageSize}`,
  );
}

export function getPostPreview(
  tableId: number,
  siteColumnId?: number | null,
): Promise<AutotoolPostPreview> {
  const qs =
    siteColumnId != null ? `?site_column_id=${siteColumnId}` : "";
  return api<AutotoolPostPreview>(
    `/autotool/tables/${tableId}/post-preview${qs}`,
  );
}
