import { api } from "@/lib/api";

export interface ErrorLogListItem {
  id: number;
  created_at: string;
  source: string;
  category: string;
  user_id: number | null;
  user_email: string | null;
  provider: string | null;
  status_code: number | null;
  message: string;
  resource_type: string | null;
  resource_id: string | null;
}

export interface ErrorLogDetail extends ErrorLogListItem {
  context_json: Record<string, unknown>;
  stack_trace: string | null;
}

export interface ErrorLogListResponse {
  items: ErrorLogListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ErrorFilterOptions {
  sources: string[];
  categories: string[];
  providers: string[];
}

export interface ErrorFilters {
  source?: string;
  category?: string;
  provider?: string;
  user_id?: number;
  since?: string; // ISO
  until?: string; // ISO
  q?: string;
  page?: number;
  page_size?: number;
}

function qs(filters: ErrorFilters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function listErrors(filters: ErrorFilters = {}) {
  return api<ErrorLogListResponse>(`/errors${qs(filters)}`);
}

export function getError(id: number) {
  return api<ErrorLogDetail>(`/errors/${id}`);
}

export function deleteError(id: number) {
  return api<void>(`/errors/${id}`, { method: "DELETE" });
}

export function listFilterOptions() {
  return api<ErrorFilterOptions>(`/errors/categories`);
}

export function getRetention() {
  return api<{ days: number; allowed: number[] }>(`/errors/retention`);
}

export function setRetention(days: number) {
  return api<{ days: number; allowed: number[] }>(`/errors/retention`, {
    method: "PUT",
    body: { days },
  });
}

export function purgeOld() {
  return api<{ deleted: number }>(`/errors/purge`, { method: "POST" });
}

export interface FrontendErrorReport {
  message: string;
  stack?: string;
  url?: string;
  user_agent?: string;
  component?: string;
  extra?: Record<string, unknown>;
}

export function reportFrontendError(payload: FrontendErrorReport) {
  return api<void>(`/errors/frontend`, { method: "POST", body: payload });
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "acm_token";

export function buildExportUrl(opts: {
  ids?: number[];
  filters?: ErrorFilters;
}): string {
  const p = new URLSearchParams();
  if (opts.ids && opts.ids.length > 0) {
    p.set("ids", opts.ids.join(","));
  } else if (opts.filters) {
    for (const [k, v] of Object.entries(opts.filters)) {
      if (v === undefined || v === null || v === "") continue;
      if (k === "page" || k === "page_size") continue;
      p.set(k, String(v));
    }
  }
  const qs = p.toString();
  return `${API_URL}/errors/export.csv${qs ? `?${qs}` : ""}`;
}

export async function downloadExport(opts: {
  ids?: number[];
  filters?: ErrorFilters;
}): Promise<void> {
  const token =
    typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_KEY) : null;
  const res = await fetch(buildExportUrl(opts), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Export failed (${res.status})`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? `error_logs_${Date.now()}.csv`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
