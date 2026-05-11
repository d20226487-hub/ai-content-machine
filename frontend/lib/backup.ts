import { api } from "@/lib/api";

export interface BackupConfig {
  schedule_enabled: boolean;
  schedule_hour_utc: number;
  s3_enabled: boolean;
  s3_endpoint_url: string | null;
  s3_region: string | null;
  s3_bucket: string | null;
  s3_access_key_id: string | null;
  s3_secret_access_key_configured: boolean;
  s3_prefix: string;
  local_retention_days: number;
  s3_retention_days: number;
}

export interface BackupConfigUpdate {
  schedule_enabled?: boolean;
  schedule_hour_utc?: number;
  s3_enabled?: boolean;
  s3_endpoint_url?: string | null;
  s3_region?: string | null;
  s3_bucket?: string | null;
  s3_access_key_id?: string | null;
  s3_secret_access_key?: string | null;
  s3_prefix?: string | null;
  local_retention_days?: number | null;
  s3_retention_days?: number | null;
}

export interface BackupRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "failed";
  filename: string | null;
  size_bytes: number | null;
  local_path: string | null;
  s3_key: string | null;
  trigger: "manual" | "scheduled";
  error: string | null;
}

export interface BackupTestResult {
  ok: boolean;
  message: string;
}

export const getBackupConfig = () => api<BackupConfig>("/backup/config");

export const updateBackupConfig = (payload: BackupConfigUpdate) =>
  api<BackupConfig>("/backup/config", { method: "PUT", body: payload });

export const testBackupConnection = () =>
  api<BackupTestResult>("/backup/test", { method: "POST" });

export const triggerBackupNow = () =>
  api<{ task_id: string }>("/backup/run", { method: "POST" });

export const listBackupRuns = (limit = 30) =>
  api<BackupRun[]>(`/backup/runs?limit=${limit}`);
