"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  bulkPermanentlyDeleteDomains,
  bulkRestoreDomains,
  emptyDomainTrash,
  getDomainTrashRetention,
  listDomainTrash,
  permanentlyDeleteDomain,
  restoreDomain,
  type Domain,
  type TrashRetention,
} from "@/lib/domains";

export default function DomainTrashPage() {
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const [items, setItems] = useState<Domain[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [retention, setRetention] = useState<TrashRetention | null>(null);

  const isAuthorized = user && ["admin", "manager"].includes(user.role.name);

  const refresh = useCallback(async () => {
    try {
      const list = await listDomainTrash();
      setItems(list);
      setSelected((cur) => {
        const onPage = new Set(list.map((i) => i.id));
        const next = new Set<number>();
        for (const id of cur) if (onPage.has(id)) next.add(id);
        return next;
      });
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
    }
  }, [t]);

  useEffect(() => {
    if (isAuthorized) void refresh();
  }, [isAuthorized, refresh]);

  useEffect(() => {
    if (isAuthorized) {
      getDomainTrashRetention()
        .then(setRetention)
        .catch(() => {
          // non-critical
        });
    }
  }, [isAuthorized]);

  const allSelected = useMemo(
    () => items !== null && items.length > 0 && items.every((i) => selected.has(i.id)),
    [items, selected],
  );

  function toggleSelectAll() {
    if (!items) return;
    setSelected(allSelected ? new Set() : new Set(items.map((i) => i.id)));
  }

  function toggleOne(id: number) {
    setSelected((cur) => {
      const n = new Set(cur);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function onRestore(id: number) {
    setBusy(true);
    try {
      await restoreDomain(id);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onDeletePermanent(d: Domain) {
    if (!confirm(t("domains.trash.confirmDeletePermanent", { name: d.name }))) return;
    setBusy(true);
    try {
      await permanentlyDeleteDomain(d.id);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onBulkRestore() {
    if (selected.size === 0) return;
    setBusy(true);
    try {
      const { restored } = await bulkRestoreDomains(Array.from(selected));
      alert(t("domains.trash.restored", { count: restored }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onBulkDelete() {
    if (selected.size === 0) return;
    if (!confirm(t("domains.trash.confirmDeleteSelected", { count: selected.size }))) return;
    setBusy(true);
    try {
      const { deleted } = await bulkPermanentlyDeleteDomains(Array.from(selected));
      alert(t("domains.trash.deleted", { count: deleted }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onEmptyTrash() {
    if (!items || items.length === 0) return;
    if (!confirm(t("domains.trash.confirmEmpty", { count: items.length }))) return;
    setBusy(true);
    try {
      const { deleted } = await emptyDomainTrash();
      alert(t("domains.trash.deleted", { count: deleted }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (authLoading || !user || !isAuthorized) return null;

  const subtitle = retention
    ? retention.days > 0
      ? t("domains.trash.subtitle", { days: retention.days })
      : t("domains.trash.subtitleManual")
    : "";

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="mb-1 text-xs">
        <Link
          href="/publish/domains"
          className="text-neutral-500 hover:text-neutral-900 hover:underline dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          ← {t("domains.title")}
        </Link>
      </div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("domains.trash.title")}
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {subtitle}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {selected.size > 0 && (
            <>
              <button
                type="button"
                onClick={onBulkRestore}
                disabled={busy}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("domains.trash.restoreSelected")} ({selected.size})
              </button>
              {/* Destructive — kept as quiet text link, not a bordered CTA,
                  so it doesn't invite a click. Restore is the primary action
                  on this page; this is the "and if you really mean it" fallback. */}
              <button
                type="button"
                onClick={onBulkDelete}
                disabled={busy}
                className="px-2 py-1 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
              >
                {t("domains.trash.deleteSelected")} ({selected.size})
              </button>
            </>
          )}
          {items && items.length > 0 && (
            <button
              type="button"
              onClick={onEmptyTrash}
              disabled={busy}
              className="px-2 py-1 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
            >
              {t("domains.trash.emptyAll")}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {items === null && (
        <p className="text-sm text-neutral-500">{t("common.loading")}</p>
      )}

      {items !== null && items.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400">
          {t("domains.trash.empty")}
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="divide-y divide-neutral-200 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
          <li className="flex items-center gap-3 bg-neutral-50 px-5 py-2 text-xs text-neutral-600 dark:bg-neutral-900/50 dark:text-neutral-400">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleSelectAll}
              className="h-3.5 w-3.5"
              aria-label={t("domains.trash.selectAll")}
            />
            <span>{t("domains.trash.selectAll")}</span>
          </li>
          {items.map((d) => (
            <li
              key={d.id}
              className="flex items-start gap-3 px-5 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
            >
              <input
                type="checkbox"
                checked={selected.has(d.id)}
                onChange={() => toggleOne(d.id)}
                className="mt-1 h-3.5 w-3.5"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {d.name}
                </p>
                <p className="mt-0.5 truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
                  {d.base_url} · {d.cms_type}
                  {d.languages.length > 0 && ` · ${d.languages.join(", ")}`}
                </p>
                {d.deleted_at && (
                  <p className="mt-0.5 text-[11px] text-neutral-400 dark:text-neutral-500">
                    {t("domains.trash.deletedAt", {
                      time: new Date(d.deleted_at).toLocaleString(),
                    })}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => onRestore(d.id)}
                  disabled={busy}
                  className="font-medium text-neutral-700 hover:underline disabled:opacity-50 dark:text-neutral-300"
                >
                  {t("domains.trash.restore")}
                </button>
                {/* Per-row destructive — same muting as the toolbar
                    buttons: red text only, smaller, no border, opacity
                    knocked down a touch so it doesn't catch the eye
                    before Restore does. */}
                <button
                  type="button"
                  onClick={() => onDeletePermanent(d)}
                  disabled={busy}
                  className="text-red-500/60 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
                >
                  {t("domains.trash.deletePermanent")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
