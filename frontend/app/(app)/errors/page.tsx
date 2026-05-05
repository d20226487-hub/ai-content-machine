"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ErrorDetailDrawer } from "@/components/ErrorDetailDrawer";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  deleteError,
  downloadExport,
  getRetention,
  listErrors,
  listFilterOptions,
  purgeOld,
  setRetention,
  type ErrorFilterOptions,
  type ErrorFilters,
  type ErrorLogListItem,
} from "@/lib/errors";

const PAGE_SIZE = 50;

function badge(text: string, color: "red" | "amber" | "blue" | "neutral" | "violet") {
  const palette: Record<string, string> = {
    red: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
    amber: "bg-amber-50 text-amber-800 ring-amber-600/10 dark:bg-amber-950/40 dark:text-amber-400 dark:ring-amber-400/30",
    blue: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
    violet: "bg-violet-50 text-violet-700 ring-violet-600/10 dark:bg-violet-950/40 dark:text-violet-400 dark:ring-violet-400/30",
    neutral:
      "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${palette[color]}`}
    >
      {text}
    </span>
  );
}

function sourceBadge(source: string) {
  if (source === "api") return badge("api", "blue");
  if (source === "worker") return badge("worker", "violet");
  if (source === "frontend") return badge("frontend", "amber");
  return badge(source, "neutral");
}

function categoryBadge(category: string) {
  const reds = new Set(["unhandled", "task_failure", "provider_error"]);
  return badge(category, reds.has(category) ? "red" : "neutral");
}

export default function ErrorsPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const [items, setItems] = useState<ErrorLogListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filterOptions, setFilterOptions] = useState<ErrorFilterOptions | null>(null);
  const [filters, setFilters] = useState<ErrorFilters>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [retentionAllowed, setRetentionAllowed] = useState<number[]>([]);
  const [purgeBusy, setPurgeBusy] = useState(false);
  const [purgeMessage, setPurgeMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [exportBusy, setExportBusy] = useState(false);

  const isAdmin = user?.role.name === "admin";
  const isAuthorized = user && ["admin", "manager"].includes(user.role.name);

  useEffect(() => {
    if (!authLoading && user && !isAuthorized) {
      router.replace("/dashboard");
    }
  }, [user, authLoading, isAuthorized, router]);

  const load = useCallback(async () => {
    try {
      const res = await listErrors({ ...filters, page, page_size: PAGE_SIZE });
      setItems(res.items);
      setTotal(res.total);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : t("errors.failedToLoad"));
    }
  }, [filters, page, t]);

  useEffect(() => {
    if (!isAuthorized) return;
    load();
  }, [isAuthorized, load]);

  useEffect(() => {
    if (!isAuthorized) return;
    listFilterOptions().then(setFilterOptions).catch(() => undefined);
    getRetention()
      .then((r) => {
        setRetentionDays(r.days);
        setRetentionAllowed(r.allowed);
      })
      .catch(() => undefined);
  }, [isAuthorized]);

  if (authLoading || !user) return null;
  if (!isAuthorized) return null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function patchFilter(patch: Partial<ErrorFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  }

  async function onChangeRetention(days: number) {
    try {
      const r = await setRetention(days);
      setRetentionDays(r.days);
      setPurgeMessage(t("errors.retentionUpdated", { days: r.days }));
    } catch (err) {
      setPurgeMessage(
        err instanceof ApiError ? err.message : t("errors.retentionUpdateFailed"),
      );
    }
  }

  async function onPurge() {
    if (!confirm(t("errors.confirmPurge", { days: retentionDays ?? 0 }))) return;
    setPurgeBusy(true);
    setPurgeMessage(null);
    try {
      const r = await purgeOld();
      setPurgeMessage(t("errors.purgeDeleted", { count: r.deleted }));
      await load();
    } catch (err) {
      setPurgeMessage(err instanceof ApiError ? err.message : t("errors.purgeFailed"));
    } finally {
      setPurgeBusy(false);
    }
  }

  async function onDelete(id: number) {
    if (!confirm(t("errors.confirmDeleteOne"))) return;
    try {
      await deleteError(id);
      setItems((list) => (list ? list.filter((e) => e.id !== id) : list));
      setTotal((t) => Math.max(0, t - 1));
      setSelectedIds((s) => {
        if (!s.has(id)) return s;
        const next = new Set(s);
        next.delete(id);
        return next;
      });
      if (selectedId === id) setSelectedId(null);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  function toggleRowSelected(id: number) {
    setSelectedIds((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePageSelected() {
    if (!items) return;
    const pageIds = items.map((i) => i.id);
    const allOnPageSelected = pageIds.every((id) => selectedIds.has(id));
    setSelectedIds((s) => {
      const next = new Set(s);
      if (allOnPageSelected) {
        for (const id of pageIds) next.delete(id);
      } else {
        for (const id of pageIds) next.add(id);
      }
      return next;
    });
  }

  async function exportSelected() {
    if (selectedIds.size === 0) return;
    setExportBusy(true);
    try {
      await downloadExport({ ids: Array.from(selectedIds) });
    } catch (err) {
      alert(err instanceof Error ? err.message : t("common.exportFailed"));
    } finally {
      setExportBusy(false);
    }
  }

  async function exportAllMatching() {
    setExportBusy(true);
    try {
      await downloadExport({ filters });
    } catch (err) {
      alert(err instanceof Error ? err.message : t("common.exportFailed"));
    } finally {
      setExportBusy(false);
    }
  }

  const allOnPageSelected = !!items && items.length > 0 && items.every((i) => selectedIds.has(i.id));
  const someOnPageSelected = !!items && items.some((i) => selectedIds.has(i.id));

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("errors.title")}
          </h1>
          <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">
            {total.toLocaleString()} {t("errors.totalSuffix")}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={exportSelected}
            disabled={exportBusy || selectedIds.size === 0}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("errors.exportSelected", { count: selectedIds.size })}
          </button>
          <button
            onClick={exportAllMatching}
            disabled={exportBusy}
            className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
            title={t("errors.exportAllHint")}
          >
            {t("errors.exportAllMatching")}
          </button>
          {retentionDays !== null && (
            <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
              {t("errors.retention")}
              <select
                disabled={!isAdmin}
                value={retentionDays}
                onChange={(e) => onChangeRetention(Number(e.target.value))}
                className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {retentionAllowed.map((d) => (
                  <option key={d} value={d}>
                    {d} {t("errors.daysSuffix")}
                  </option>
                ))}
              </select>
            </label>
          )}
          {isAdmin && (
            <button
              onClick={onPurge}
              disabled={purgeBusy}
              className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {purgeBusy ? t("errors.purging") : t("errors.purgeOld")}
            </button>
          )}
        </div>
      </div>

      {purgeMessage && (
        <div className="mb-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
          {purgeMessage}
        </div>
      )}

      <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-5">
        <input
          placeholder={t("errors.searchPlaceholder")}
          value={filters.q ?? ""}
          onChange={(e) => patchFilter({ q: e.target.value || undefined })}
          className="col-span-2 rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        <select
          value={filters.source ?? ""}
          onChange={(e) => patchFilter({ source: e.target.value || undefined })}
          className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("errors.allSources")}</option>
          {(filterOptions?.sources ?? []).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={filters.category ?? ""}
          onChange={(e) => patchFilter({ category: e.target.value || undefined })}
          className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("errors.allCategories")}</option>
          {(filterOptions?.categories ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          value={filters.provider ?? ""}
          onChange={(e) => patchFilter({ provider: e.target.value || undefined })}
          className="rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          <option value="">{t("errors.allProviders")}</option>
          {(filterOptions?.providers ?? []).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      {loadError && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <table className="min-w-full divide-y divide-neutral-200 text-sm dark:divide-neutral-800">
          <thead className="bg-neutral-50 dark:bg-neutral-900/50">
            <tr className="text-left text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <th className="px-3 py-2">
                <input
                  type="checkbox"
                  aria-label={t("errors.selectAllOnPage")}
                  checked={allOnPageSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = !allOnPageSelected && someOnPageSelected;
                  }}
                  onChange={togglePageSelected}
                />
              </th>
              <th className="px-3 py-2">{t("errors.colTime")}</th>
              <th className="px-3 py-2">{t("errors.colSource")}</th>
              <th className="px-3 py-2">{t("errors.colCategory")}</th>
              <th className="px-3 py-2">{t("errors.colProvider")}</th>
              <th className="px-3 py-2">{t("errors.colStatus")}</th>
              <th className="px-3 py-2">{t("errors.colUser")}</th>
              <th className="px-3 py-2">{t("errors.colMessage")}</th>
              {isAdmin && <th className="px-3 py-2"></th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {items === null && (
              <tr>
                <td colSpan={isAdmin ? 9 : 8} className="px-3 py-8 text-center text-neutral-500">
                  {t("common.loading")}
                </td>
              </tr>
            )}
            {items !== null && items.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 9 : 8} className="px-3 py-8 text-center text-neutral-500">
                  {t("errors.noneMatch")}
                </td>
              </tr>
            )}
            {items?.map((row) => (
              <tr
                key={row.id}
                onClick={() => setSelectedId(row.id)}
                className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-800/50"
              >
                <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label={t("errors.selectRowAria", { id: row.id })}
                    checked={selectedIds.has(row.id)}
                    onChange={() => toggleRowSelected(row.id)}
                  />
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-xs text-neutral-600 dark:text-neutral-400">
                  {new Date(row.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2">{sourceBadge(row.source)}</td>
                <td className="px-3 py-2">{categoryBadge(row.category)}</td>
                <td className="px-3 py-2 text-neutral-600 dark:text-neutral-400">
                  {row.provider ?? "—"}
                </td>
                <td className="px-3 py-2 text-neutral-600 dark:text-neutral-400">
                  {row.status_code ?? "—"}
                </td>
                <td className="max-w-[160px] truncate px-3 py-2 text-neutral-600 dark:text-neutral-400">
                  {row.user_email ?? "—"}
                </td>
                <td className="max-w-[420px] truncate px-3 py-2 text-neutral-800 dark:text-neutral-200">
                  {row.message}
                </td>
                {isAdmin && (
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(row.id);
                      }}
                      className="text-xs text-neutral-500 hover:text-red-600 dark:hover:text-red-400"
                    >
                      {t("common.delete")}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm text-neutral-600 dark:text-neutral-400">
        <span>
          {t("common.pageXofY", { page, total: totalPages })}
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-md border border-neutral-300 px-3 py-1 disabled:opacity-50 dark:border-neutral-700"
          >
            {t("common.previous")}
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-md border border-neutral-300 px-3 py-1 disabled:opacity-50 dark:border-neutral-700"
          >
            {t("common.next")}
          </button>
        </div>
      </div>

      {selectedId !== null && (
        <ErrorDetailDrawer
          errorId={selectedId}
          onClose={() => setSelectedId(null)}
          onDelete={isAdmin ? onDelete : undefined}
        />
      )}
    </main>
  );
}
