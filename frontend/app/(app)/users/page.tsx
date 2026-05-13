"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { UserModal } from "@/components/UserModal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import {
  formatUsd,
  listUserSpend,
  type UserSpendSummary,
} from "@/lib/spend";
import {
  deleteUser,
  getUserTrashCount,
  listRoles,
  listUsers,
} from "@/lib/users";
import type { Role, User } from "@/lib/types";

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; user: User };

export default function UsersPage() {
  const router = useRouter();
  const { user: actor, loading: authLoading } = useAuth();
  const { t } = useT();

  const [users, setUsers] = useState<User[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [spendByUser, setSpendByUser] = useState<Record<number, UserSpendSummary>>({});
  const [orphanSpend, setOrphanSpend] = useState<UserSpendSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [trashCount, setTrashCount] = useState(0);

  const refreshTrashCount = useCallback(async () => {
    try {
      const { count } = await getUserTrashCount();
      setTrashCount(count);
    } catch {
      // non-critical; the badge just won't show
    }
  }, []);

  useEffect(() => {
    if (!authLoading && actor && !["admin", "manager"].includes(actor.role.name)) {
      router.replace("/dashboard");
    }
  }, [actor, authLoading, router]);

  useEffect(() => {
    if (!actor || !["admin", "manager"].includes(actor.role.name)) return;
    let ignored = false;
    Promise.all([listUsers(), listRoles(), listUserSpend()])
      .then(([u, r, s]) => {
        if (ignored) return;
        setUsers(u);
        setRoles(r);
        const byId: Record<number, UserSpendSummary> = {};
        let orphan: UserSpendSummary | null = null;
        for (const row of s) {
          if (row.user_id == null) orphan = row;
          else byId[row.user_id] = row;
        }
        setSpendByUser(byId);
        setOrphanSpend(orphan);
      })
      .catch((err) => {
        if (ignored) return;
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
      });
    void refreshTrashCount();
    return () => {
      ignored = true;
    };
  }, [actor, t, refreshTrashCount]);

  if (authLoading || !actor) return null;

  function upsert(u: User) {
    setUsers((list) => {
      if (!list) return [u];
      const i = list.findIndex((x) => x.id === u.id);
      if (i === -1) return [...list, u];
      const copy = list.slice();
      copy[i] = u;
      return copy;
    });
  }

  async function onDelete(target: User) {
    if (!confirm(t("users.confirmDelete", { email: target.email }))) return;
    try {
      await deleteUser(target.id);
      setUsers((list) => (list ? list.filter((u) => u.id !== target.id) : list));
      await refreshTrashCount();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  function canEdit(target: User): boolean {
    if (!actor) return false;
    if (actor.role.name === "admin") return true;
    return target.role.name !== "admin"; // manager
  }

  function canDelete(target: User): boolean {
    if (!actor) return false;
    if (target.id === actor.id) return false;
    return canEdit(target);
  }

  return (
    <main className="mx-auto max-w-7xl p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">{t("users.title")}</h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("users.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {trashCount > 0 && (
            <Link
              href="/users/trash"
              className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-600 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
            >
              {t("users.trashLinkWithCount", { count: trashCount })}
            </Link>
          )}
          <button
            onClick={() => setModal({ kind: "create" })}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200"
          >
            {t("users.newButton")}
          </button>
        </div>
      </div>

      {loadError && (
        <p className="mt-6 rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {loadError}
        </p>
      )}

      {!users && !loadError && (
        <p className="mt-8 text-sm text-neutral-500 dark:text-neutral-400">{t("users.loading")}</p>
      )}

      {users && (
        <div className="mt-8 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-950 text-left text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <tr>
                <th className="px-4 py-3 font-medium">{t("users.colEmail")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colName")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colRole")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colActive")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colCreated")}</th>
                <th
                  className="px-4 py-3 font-medium"
                  title={t("users.colSpendHint")}
                >
                  {t("users.colSpend")}
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800">
                  <td className="px-4 py-3 text-neutral-900 dark:text-neutral-100">
                    {u.email}
                    {u.id === actor.id && (
                      <span className="ml-2 rounded-full bg-neutral-200 px-2 py-0.5 text-[10px] uppercase tracking-wide text-neutral-700 dark:bg-neutral-700 dark:text-neutral-200">
                        {t("users.you")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-neutral-700 dark:text-neutral-300">
                    {u.full_name ?? <span className="text-neutral-400 dark:text-neutral-500">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-700 dark:text-neutral-300">
                    {u.role.name}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="text-green-600 dark:text-green-400">{t("common.yes")}</span>
                    ) : (
                      <span className="text-neutral-400 dark:text-neutral-500">{t("common.no")}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-neutral-500 dark:text-neutral-400">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 align-top">
                    <SpendCell
                      summary={spendByUser[u.id]}
                      labels={{
                        today: t("users.spendToday"),
                        week: t("users.spendWeek"),
                        month: t("users.spendMonth"),
                        all: t("users.spendAll"),
                        events: t("users.spendEvents"),
                      }}
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-3 text-sm">
                      {canEdit(u) && (
                        <button
                          onClick={() => setModal({ kind: "edit", user: u })}
                          className="font-medium text-neutral-700 dark:text-neutral-300 hover:underline"
                        >
                          {t("common.edit")}
                        </button>
                      )}
                      {canDelete(u) && (
                        <button
                          onClick={() => onDelete(u)}
                          className="font-medium text-red-600 dark:text-red-400 hover:underline"
                        >
                          {t("common.delete")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {orphanSpend && (
        <p className="mt-3 text-xs text-neutral-500 dark:text-neutral-400">
          {t("users.orphanSpend", {
            month: formatUsd(orphanSpend.spend.this_month_usd),
            all: formatUsd(orphanSpend.spend.all_time_usd),
          })}
        </p>
      )}

      {modal.kind === "create" && (
        <UserModal
          mode="create"
          roles={roles}
          actor={actor}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={upsert}
        />
      )}
      {modal.kind === "edit" && (
        <UserModal
          mode="edit"
          user={modal.user}
          roles={roles}
          actor={actor}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={upsert}
        />
      )}
    </main>
  );
}

/** Inline spend cell: month value prominent, daily/week/all-time inline below.
 * Anything zero collapses to "—" so the column doesn't look noisy when
 * pricing isn't configured yet or no usage has been recorded. */
function SpendCell({
  summary,
  labels,
}: {
  summary?: UserSpendSummary;
  labels: { today: string; week: string; month: string; all: string; events: string };
}) {
  if (!summary) {
    return <span className="text-neutral-400 dark:text-neutral-500">—</span>;
  }
  const s = summary.spend;
  const eventsLabel = (n: number) => `${n.toLocaleString()} ${labels.events}`;
  return (
    <div className="min-w-[14rem]">
      <div className="font-mono text-sm tabular-nums text-neutral-900 dark:text-neutral-100">
        {formatUsd(s.this_month_usd)}
        <span className="ml-1 text-[10px] font-normal uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
          {labels.month}
        </span>
      </div>
      <div className="mt-0.5 font-mono text-[10px] tabular-nums text-neutral-500 dark:text-neutral-400">
        <span title={eventsLabel(s.today_events)}>
          {labels.today} {formatUsd(s.today_usd)}
        </span>
        <span className="mx-2 text-neutral-300 dark:text-neutral-600">·</span>
        <span title={eventsLabel(s.this_week_events)}>
          {labels.week} {formatUsd(s.this_week_usd)}
        </span>
        <span className="mx-2 text-neutral-300 dark:text-neutral-600">·</span>
        <span title={eventsLabel(s.all_time_events)}>
          {labels.all} {formatUsd(s.all_time_usd)}
        </span>
      </div>
    </div>
  );
}
