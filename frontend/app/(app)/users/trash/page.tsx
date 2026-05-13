"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { UserChip } from "@/components/UserChip";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  bulkPermanentlyDeleteUsers,
  bulkRestoreUsers,
  emptyUserTrash,
  getUserTrashRetention,
  listUserTrash,
  permanentlyDeleteUser,
  restoreUser,
  type TrashRetention,
} from "@/lib/users";
import type { User } from "@/lib/types";

export default function UserTrashPage() {
  const router = useRouter();
  const { user: actor, loading: authLoading } = useAuth();
  const { t } = useT();

  const [items, setItems] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [retention, setRetention] = useState<TrashRetention | null>(null);

  const isAuthorized =
    actor && ["admin", "manager"].includes(actor.role.name);

  useEffect(() => {
    if (!authLoading && actor && !isAuthorized) {
      router.replace("/dashboard");
    }
  }, [actor, authLoading, isAuthorized, router]);

  const refresh = useCallback(async () => {
    try {
      const list = await listUserTrash();
      setItems(list);
      setSelected((cur) => {
        const onPage = new Set(list.map((u) => u.id));
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
      getUserTrashRetention()
        .then(setRetention)
        .catch(() => {
          // non-critical
        });
    }
  }, [isAuthorized]);

  const allSelected = useMemo(
    () => items !== null && items.length > 0 && items.every((u) => selected.has(u.id)),
    [items, selected],
  );

  function toggleSelectAll() {
    if (!items) return;
    setSelected(allSelected ? new Set() : new Set(items.map((u) => u.id)));
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
      await restoreUser(id);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onDeletePermanent(u: User) {
    if (!confirm(t("users.trash.confirmDeletePermanent", { email: u.email }))) return;
    setBusy(true);
    try {
      await permanentlyDeleteUser(u.id);
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
      const r = await bulkRestoreUsers(Array.from(selected));
      let msg = t("users.trash.restored", { count: r.restored });
      if (r.skipped_email_conflicts.length > 0) {
        msg +=
          "\n\n" +
          t("users.trash.skippedConflicts", {
            count: r.skipped_email_conflicts.length,
            emails: r.skipped_email_conflicts.join(", "),
          });
      }
      alert(msg);
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onBulkDelete() {
    if (selected.size === 0) return;
    if (!confirm(t("users.trash.confirmDeleteSelected", { count: selected.size }))) return;
    setBusy(true);
    try {
      const { deleted } = await bulkPermanentlyDeleteUsers(Array.from(selected));
      alert(t("users.trash.deleted", { count: deleted }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function onEmptyTrash() {
    if (!items || items.length === 0) return;
    if (!confirm(t("users.trash.confirmEmpty", { count: items.length }))) return;
    setBusy(true);
    try {
      const { deleted } = await emptyUserTrash();
      alert(t("users.trash.deleted", { count: deleted }));
      await refresh();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : t("common.actionFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (authLoading || !actor || !isAuthorized) return null;

  const subtitle = retention
    ? retention.days > 0
      ? t("users.trash.subtitle", { days: retention.days })
      : t("users.trash.subtitleManual")
    : "";

  return (
    <main className="mx-auto max-w-6xl p-10">
      <div className="mb-1 text-xs">
        <Link
          href="/users"
          className="text-neutral-500 hover:text-neutral-900 hover:underline dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          ← {t("users.title")}
        </Link>
      </div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("users.trash.title")}
          </h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {subtitle}
          </p>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("users.trash.adminHint")}
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
                {t("users.trash.restoreSelected")} ({selected.size})
              </button>
              <button
                type="button"
                onClick={onBulkDelete}
                disabled={busy}
                className="px-2 py-1 text-sm text-red-500/60 underline-offset-2 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
              >
                {t("users.trash.deleteSelected")} ({selected.size})
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
              {t("users.trash.emptyAll")}
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
          {t("users.trash.empty")}
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
              aria-label={t("users.trash.selectAll")}
            />
            <span>{t("users.trash.selectAll")}</span>
          </li>
          {items.map((u) => (
            <li
              key={u.id}
              className="flex items-start gap-3 px-5 py-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/40"
            >
              <input
                type="checkbox"
                checked={selected.has(u.id)}
                onChange={() => toggleOne(u.id)}
                className="mt-1 h-3.5 w-3.5"
              />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                  {u.full_name || u.email}
                  {u.role?.name && (
                    <span
                      className={
                        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide " +
                        (u.role.name === "admin"
                          ? "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                          : u.role.name === "manager"
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                          : "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300")
                      }
                    >
                      {u.role.name}
                    </span>
                  )}
                </p>
                <p className="mt-0.5 truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">
                  {u.email}
                </p>
                {u.deleted_at && (
                  <p className="mt-0.5 text-[11px] text-neutral-400 dark:text-neutral-500">
                    {t("users.trash.deletedAt", {
                      time: new Date(u.deleted_at).toLocaleString(),
                    })}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <UserChip name={u.full_name || u.email} />
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => onRestore(u.id)}
                    disabled={busy}
                    className="font-medium text-neutral-700 hover:underline disabled:opacity-50 dark:text-neutral-300"
                  >
                    {t("users.trash.restore")}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeletePermanent(u)}
                    disabled={busy}
                    className="text-red-500/60 hover:text-red-700 hover:underline disabled:opacity-50 dark:text-red-400/40 dark:hover:text-red-300"
                  >
                    {t("users.trash.deletePermanent")}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
