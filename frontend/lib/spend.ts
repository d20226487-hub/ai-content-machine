import { api } from "@/lib/api";

/** Decimals come back from the API as strings (Pydantic preserves precision).
 * The UI parses to number for display only. */
export interface SpendWindow {
  today_usd: string;
  today_events: number;
  this_week_usd: string;
  this_week_events: number;
  this_month_usd: string;
  this_month_events: number;
  all_time_usd: string;
  all_time_events: number;
}

export interface UserSpendSummary {
  user_id: number | null;
  user_email: string | null;
  user_name: string | null;
  spend: SpendWindow;
}

export interface PricingTableRow {
  provider_code: string;
  model: string;
  input_per_1m: string | null;
  output_per_1m: string | null;
}

export const listUserSpend = () =>
  api<UserSpendSummary[]>("/users/spend");

export const getUserSpend = (userId: number) =>
  api<SpendWindow>(`/users/${userId}/spend`);

export const getPricing = () =>
  api<PricingTableRow[]>("/settings/pricing");

export const putPricing = (rates: PricingTableRow[]) =>
  api<PricingTableRow[]>("/settings/pricing", {
    method: "PUT",
    body: { rates },
  });

/** Format a USD string for display: $0.0008 → "$0.0008" with sensible
 * precision. Empty/zero values render as "—" so the table doesn't read
 * as a row of $0.00 noise. */
export function formatUsd(s: string | null | undefined): string {
  if (s == null) return "—";
  const n = Number(s);
  if (!Number.isFinite(n) || n === 0) return "—";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}
