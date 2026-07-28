"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { SearchableSelect } from "@/components/SearchableSelect";
import { ApiError } from "@/lib/api";
import { useT, type Lang } from "@/lib/i18n-context";
import {
  getStats,
  type StatMetrics,
  type StatsGroupBy,
  type StatsResponse,
} from "@/lib/stats";

const PERIODS = [3, 6, 12, 24] as const;
const GROUP_BYS: StatsGroupBy[] = ["user", "table", "domain", "channel"];

function fmtInt(n: number | null, lang: Lang): string {
  return n == null ? "—" : n.toLocaleString(lang === "ru" ? "ru-RU" : "en-US");
}

function fmtCost(n: number | null): string {
  if (n == null) return "—";
  const digits = n > 0 && n < 1 ? 4 : 2;
  return "$" + n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  });
}

function fmtTokens(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function monthLabel(m: string, lang: Lang): string {
  const [y, mm] = m.split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-US", {
    month: "long",
    year: "numeric",
  }).format(new Date(y, (mm || 1) - 1, 1));
}

export default function StatsPage() {
  const { t, lang } = useT();

  const [months, setMonths] = useState(12);
  const [month, setMonth] = useState<string>(""); // "" = all months in period
  const [userId, setUserId] = useState<number | "">("");
  const [domainId, setDomainId] = useState<number | "">("");
  const [onlyContent, setOnlyContent] = useState(false);
  const [groupBy, setGroupBy] = useState<StatsGroupBy>("user");

  const [data, setData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await getStats({
          month: month || null,
          months,
          user_id: userId === "" ? null : userId,
          domain_id: domainId === "" ? null : domainId,
          group_by: groupBy,
          only_content: onlyContent,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [month, months, userId, domainId, groupBy, onlyContent]);

  useEffect(() => {
    void load();
  }, [load]);

  const filters = data?.filters;
  const domainScoped = data?.domain_scoped ?? false;

  // Month dropdown is connected to the selected period: only real (data)
  // months that fall within the last `months` window are offered.
  const periodStart = useMemo(() => {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - (months - 1));
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  }, [months]);
  const monthOptions = useMemo(
    () => (filters?.months ?? []).filter((m) => m >= periodStart),
    [filters, periodStart],
  );
  // If the chosen month falls outside the current period window, clear it.
  useEffect(() => {
    if (month && filters && !monthOptions.includes(month)) setMonth("");
  }, [month, monthOptions, filters]);

  // Success metric <td>s shared by month rows, totals, and breakdown rows.
  const metricCells = useMemo(
    () =>
      function MetricCells(m: StatMetrics) {
        return (
          <>
            <td className="px-3 py-2 text-right tabular-nums">{fmtInt(m.gen_runs, lang)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{fmtInt(m.gen_cells, lang)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{fmtInt(m.pub_custom, lang)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{fmtInt(m.pub_autotool, lang)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{fmtCost(m.cost_usd)}</td>
            <td className="px-3 py-2 text-right tabular-nums">{fmtTokens(m.tokens)}</td>
          </>
        );
      },
    [lang],
  );

  const headCells = (
    <>
      <th className="px-3 py-2 text-right font-medium" title={t("stats.colRunsHint")}>
        {t("stats.colRuns")}
      </th>
      <th className="px-3 py-2 text-right font-medium" title={t("stats.colCellsHint")}>
        {t("stats.colCells")}
      </th>
      <th className="px-3 py-2 text-right font-medium">{t("stats.colCustom")}</th>
      <th className="px-3 py-2 text-right font-medium">{t("stats.colAutotool")}</th>
      <th className="px-3 py-2 text-right font-medium">{t("stats.colCost")}</th>
      <th className="px-3 py-2 text-right font-medium">{t("stats.colTokens")}</th>
    </>
  );

  // Failure count cell: red when > 0, muted otherwise, "—" when N/A.
  const errCell = (n: number | null) => (
    <td
      className={
        "px-3 py-2 text-right tabular-nums " +
        (n && n > 0
          ? "text-red-600 dark:text-red-400"
          : "text-neutral-400 dark:text-neutral-600")
      }
    >
      {n == null ? "—" : fmtInt(n, lang)}
    </td>
  );

  const errorRow = (label: string, m: StatMetrics, key: string) => (
    <tr key={key} className="text-neutral-700 dark:text-neutral-300">
      <td className="px-3 py-2 font-medium text-neutral-900 dark:text-neutral-100">
        {label}
      </td>
      {errCell(m.gen_failed)}
      {errCell(m.pub_custom_failed)}
      {errCell(m.pub_autotool_failed)}
    </tr>
  );

  const selectCls =
    "rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100";

  return (
    <main className="mx-auto max-w-6xl px-5 py-6">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("stats.title")}
      </h1>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("stats.subtitle")}
      </p>

      {/* Filters */}
      <section className="mt-4 flex flex-wrap items-end gap-3 rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-900">
        <label className="flex flex-col gap-1 text-xs text-neutral-600 dark:text-neutral-400">
          {t("stats.period")}
          <select
            className={selectCls}
            value={months}
            disabled={month !== ""}
            onChange={(e) => setMonths(Number(e.target.value))}
          >
            {PERIODS.map((p) => (
              <option key={p} value={p}>
                {t("stats.lastN", { n: p })}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-600 dark:text-neutral-400">
          {t("stats.month")}
          <select
            className={selectCls}
            value={month}
            onChange={(e) => setMonth(e.target.value)}
          >
            <option value="">{t("stats.allMonths")}</option>
            {monthOptions.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m, lang)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-600 dark:text-neutral-400">
          {t("stats.user")}
          <SearchableSelect
            value={userId}
            onChange={setUserId}
            options={filters?.users ?? []}
            allLabel={t("stats.allUsers")}
            className={selectCls + " w-48"}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-neutral-600 dark:text-neutral-400">
          {t("stats.domain")}
          <SearchableSelect
            value={domainId}
            onChange={setDomainId}
            options={filters?.domains ?? []}
            allLabel={t("stats.allDomains")}
            className={selectCls + " w-48"}
          />
        </label>
        <label
          className="flex cursor-pointer items-center gap-1.5 pb-1 text-xs text-neutral-600 dark:text-neutral-400"
          title={t("stats.onlyContentHint")}
        >
          <input
            type="checkbox"
            checked={onlyContent}
            onChange={(e) => setOnlyContent(e.target.checked)}
          />
          {t("stats.onlyContent")}
        </label>
        {loading && (
          <span className="ml-auto text-xs text-neutral-400">{t("common.loading")}</span>
        )}
      </section>

      {domainScoped && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          {t("stats.domainScopedNote")}
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {/* By month */}
      <section className="mt-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {t("stats.byMonth")}
        </h2>
        <div className="mt-2 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-3 py-2 font-medium">{t("stats.colMonth")}</th>
                {headCells}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {data && data.months.length > 0 && (
                <tr className="bg-neutral-50 font-semibold dark:bg-neutral-900/60">
                  <td className="px-3 py-2">{t("stats.total")}</td>
                  {metricCells(data.totals)}
                </tr>
              )}
              {(data?.months ?? []).map((m) => (
                <tr key={m.month} className="text-neutral-700 dark:text-neutral-300">
                  <td className="px-3 py-2 font-medium text-neutral-900 dark:text-neutral-100">
                    {monthLabel(m.month, lang)}
                  </td>
                  {metricCells(m)}
                </tr>
              ))}
              {data && data.months.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-sm text-neutral-400">
                    {t("stats.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Errors by month */}
      <section className="mt-6">
        <h2 className="inline-flex items-center rounded-md bg-red-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-red-800 dark:bg-red-900/40 dark:text-red-300">
          {t("stats.errors")}
        </h2>
        <div className="mt-2 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-3 py-2 font-medium">{t("stats.colMonth")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colGeneration")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colCustom")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colAutotool")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {data && data.months.length > 0 && (
                <tr className="bg-neutral-50 font-semibold dark:bg-neutral-900/60">
                  <td className="px-3 py-2">{t("stats.total")}</td>
                  {errCell(data.totals.gen_failed)}
                  {errCell(data.totals.pub_custom_failed)}
                  {errCell(data.totals.pub_autotool_failed)}
                </tr>
              )}
              {(data?.months ?? []).map((m) =>
                errorRow(monthLabel(m.month, lang), m, m.month),
              )}
              {data && data.months.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-sm text-neutral-400">
                    {t("stats.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Breakdown */}
      <section className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("stats.breakdown")}
          </h2>
          <div className="flex rounded-md border border-neutral-300 p-0.5 text-sm dark:border-neutral-700">
            {GROUP_BYS.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => setGroupBy(g)}
                className={
                  "rounded px-2.5 py-1 text-xs font-medium transition-colors " +
                  (groupBy === g
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800")
                }
              >
                {t(`stats.by.${g}` as never)}
              </button>
            ))}
          </div>
        </div>
        {/* Successful */}
        <p className="mt-3">
          <span className="inline-flex items-center rounded-md bg-emerald-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
            {t("stats.successful")}
          </span>
        </p>
        <div className="mt-1 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-3 py-2 font-medium">{t(`stats.by.${groupBy}` as never)}</th>
                {headCells}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {(data?.breakdown ?? []).map((b) => (
                <tr key={b.key} className="text-neutral-700 dark:text-neutral-300">
                  <td className="max-w-xs truncate px-3 py-2 font-medium text-neutral-900 dark:text-neutral-100">
                    {b.label}
                  </td>
                  {metricCells(b)}
                </tr>
              ))}
              {data && data.breakdown.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-sm text-neutral-400">
                    {t("stats.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Errors */}
        <p className="mt-4">
          <span className="inline-flex items-center rounded-md bg-red-100 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-red-800 dark:bg-red-900/40 dark:text-red-300">
            {t("stats.errors")}
          </span>
        </p>
        <div className="mt-1 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
              <tr>
                <th className="px-3 py-2 font-medium">{t(`stats.by.${groupBy}` as never)}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colGeneration")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colCustom")}</th>
                <th className="px-3 py-2 text-right font-medium">{t("stats.colAutotool")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {(data?.breakdown ?? []).map((b) => errorRow(b.label, b, b.key))}
              {data && data.breakdown.length === 0 && !loading && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-sm text-neutral-400">
                    {t("stats.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
