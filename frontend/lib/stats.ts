import { api } from "./api";

/** A metric can be null = "not applicable to this view" (renders "—"). */
export interface StatMetrics {
  gen_runs: number | null;
  gen_cells: number | null;
  gen_failed: number | null;
  pub_custom: number | null;
  pub_custom_failed: number | null;
  pub_autotool: number | null;
  pub_autotool_failed: number | null;
  cost_usd: number | null;
  tokens: number | null;
}

export interface MonthStat extends StatMetrics {
  month: string; // "YYYY-MM"
}

export interface BreakdownRow extends StatMetrics {
  key: string;
  label: string;
}

export interface StatFilterOption {
  id: number;
  name: string;
}

export interface StatsFilters {
  users: StatFilterOption[];
  domains: StatFilterOption[];
  months: string[];
}

export type StatsGroupBy = "user" | "table" | "domain" | "channel";

export interface StatsResponse {
  months: MonthStat[];
  totals: StatMetrics;
  breakdown: BreakdownRow[];
  group_by: StatsGroupBy;
  domain_scoped: boolean;
  filters: StatsFilters;
}

export interface StatsQuery {
  month?: string | null;
  months?: number;
  user_id?: number | null;
  domain_id?: number | null;
  group_by?: StatsGroupBy;
  only_content?: boolean;
}

export function getStats(q: StatsQuery = {}): Promise<StatsResponse> {
  const sp = new URLSearchParams();
  if (q.month) sp.set("month", q.month);
  if (q.months) sp.set("months", String(q.months));
  if (q.user_id != null) sp.set("user_id", String(q.user_id));
  if (q.domain_id != null) sp.set("domain_id", String(q.domain_id));
  if (q.group_by) sp.set("group_by", q.group_by);
  if (q.only_content) sp.set("only_content", "true");
  const qs = sp.toString();
  return api<StatsResponse>(`/stats${qs ? "?" + qs : ""}`);
}
