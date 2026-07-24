"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError } from "@/lib/api";
import {
  getDashboardActivity,
  type ActivityItem,
  type ActivityResponse,
} from "@/lib/dashboard";
import { useT, type TranslationKey } from "@/lib/i18n-context";

/** Localised label for a job kind; falls back to the raw code if unknown. */
const KIND_KEYS: Record<string, TranslationKey> = {
  autotool: "dashboard.kind.autotool",
  generation: "dashboard.kind.generation",
  publish: "dashboard.kind.publish",
  gdocs_import: "dashboard.kind.gdocs_import",
  domain_cache: "dashboard.kind.domain_cache",
  language_sync: "dashboard.kind.language_sync",
  link_check: "dashboard.kind.link_check",
  link_fix: "dashboard.kind.link_fix",
  structure_format: "dashboard.kind.structure_format",
  csv_export: "dashboard.kind.csv_export",
  backup: "dashboard.kind.backup",
};

const STATUS_KEYS: Record<string, TranslationKey> = {
  running: "dashboard.status.running",
  queued: "dashboard.status.queued",
  paused: "dashboard.status.paused",
};

const STATUS_DOT: Record<string, string> = {
  running: "bg-green-500",
  queued: "bg-amber-400",
  paused: "bg-neutral-400",
};

function agoShort(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.round(h / 24)}d`;
}

/**
 * "Active processes" — an ON-DEMAND snapshot of every queued/running/paused
 * background job across all users. Deliberately pull-only: nothing is fetched
 * until the operator clicks "Check now", and there is no interval/polling, so it
 * puts no standing load on the server.
 */
export function ActiveProcessesCard() {
  const { t } = useT();
  const [data, setData] = useState<ActivityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setLoading(true);
    setError(null);
    try {
      setData(await getDashboardActivity());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.somethingWentWrong"));
    } finally {
      setLoading(false);
    }
  }

  const checkedTime = data
    ? new Date(data.checked_at).toLocaleTimeString()
    : null;

  return (
    <section className="mt-6 rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("dashboard.activityTitle")}
          </h2>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("dashboard.activitySubtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void check()}
          disabled={loading}
          className="shrink-0 rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {loading
            ? t("dashboard.activityChecking")
            : data
              ? t("dashboard.activityRefresh")
              : t("dashboard.activityCheck")}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {data && !error && (
        <div className="mt-4">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t("dashboard.activityCount", { n: data.items.length })}
            {checkedTime ? ` · ${t("dashboard.activityCheckedAt", { time: checkedTime })}` : ""}
          </p>

          {data.items.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed border-neutral-300 px-4 py-6 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
              {t("dashboard.activityEmpty")}
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
              {data.items.map((it) => (
                <ActivityRow key={`${it.kind}-${it.id}`} item={it} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function ActivityRow({ item: it }: { item: ActivityItem }) {
  const { t } = useT();
  const kind = KIND_KEYS[it.kind] ? t(KIND_KEYS[it.kind]) : it.kind;
  const status = STATUS_KEYS[it.status] ? t(STATUS_KEYS[it.status]) : it.status;
  const dot = STATUS_DOT[it.status] ?? "bg-neutral-400";
  const progress =
    it.total != null && it.total > 0 ? `${it.done ?? 0}/${it.total}` : null;
  const ago = agoShort(it.created_at ?? it.started_at);

  const body = (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5">
      <span className="flex min-w-0 items-center gap-2">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${dot}`}
          title={status}
          aria-hidden
        />
        <span className="min-w-0">
          <span className="block truncate text-sm text-neutral-800 dark:text-neutral-200">
            <span className="font-medium">{kind}</span>
            {it.label ? ` · ${it.label}` : ""}
          </span>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {status}
            {it.owner ? ` · ${t("dashboard.activityBy", { owner: it.owner })}` : ""}
            {ago ? ` · ${t("dashboard.activityAgo", { ago })}` : ""}
          </span>
        </span>
      </span>
      <span className="shrink-0 text-right">
        {progress && (
          <span className="block font-mono text-xs tabular-nums text-neutral-600 dark:text-neutral-300">
            {progress}
          </span>
        )}
        {it.detail_path && (
          <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
            {t("dashboard.activityOpen")}
          </span>
        )}
      </span>
    </div>
  );

  return (
    <li>
      {it.detail_path ? (
        <Link
          href={it.detail_path}
          className="block hover:bg-neutral-50 dark:hover:bg-neutral-800/60"
        >
          {body}
        </Link>
      ) : (
        body
      )}
    </li>
  );
}
