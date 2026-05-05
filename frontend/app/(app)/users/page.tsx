"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { UserModal } from "@/components/UserModal";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import { deleteUser, listRoles, listUsers } from "@/lib/users";
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>({ kind: "closed" });

  useEffect(() => {
    if (!authLoading && actor && !["admin", "manager"].includes(actor.role.name)) {
      router.replace("/dashboard");
    }
  }, [actor, authLoading, router]);

  useEffect(() => {
    if (!actor || !["admin", "manager"].includes(actor.role.name)) return;
    Promise.all([listUsers(), listRoles()])
      .then(([u, r]) => {
        setUsers(u);
        setRoles(r);
      })
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [actor, t]);

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
    <main className="mx-auto max-w-5xl p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">{t("users.title")}</h1>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            {t("users.subtitle")}
          </p>
        </div>
        <button
          onClick={() => setModal({ kind: "create" })}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200"
        >
          {t("users.newButton")}
        </button>
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
        <div className="mt-8 overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-950 text-left text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              <tr>
                <th className="px-4 py-3 font-medium">{t("users.colEmail")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colName")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colRole")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colActive")}</th>
                <th className="px-4 py-3 font-medium">{t("users.colCreated")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-200 dark:divide-neutral-800">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-neutral-50 dark:hover:bg-neutral-800">
                  <td className="px-4 py-3 text-neutral-900 dark:text-neutral-100">
                    {u.email}
                    {u.id === actor.id && (
                      <span className="ml-2 rounded-full bg-neutral-200 px-2 py-0.5 text-[10px] uppercase tracking-wide text-neutral-700 dark:text-neutral-300">
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
