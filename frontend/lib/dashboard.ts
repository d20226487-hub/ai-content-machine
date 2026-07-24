import { api } from "./api";

/** One in-flight background job, normalised across every job type. */
export interface ActivityItem {
  kind: string;
  id: number;
  label: string;
  owner: string | null;
  status: string; // "queued" | "running" | "paused"
  done: number | null;
  total: number | null;
  started_at: string | null;
  created_at: string | null;
  detail_path: string | null;
}

export interface ActivityResponse {
  items: ActivityItem[];
  checked_at: string;
}

/** On-demand snapshot of every queued/running/paused job across all users.
 *  Pull-only — call it when the operator clicks "Check now", never on a timer. */
export function getDashboardActivity(): Promise<ActivityResponse> {
  return api<ActivityResponse>("/dashboard/activity");
}
