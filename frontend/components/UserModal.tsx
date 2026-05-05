"use client";

import { FormEvent, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { createUser, resetUserPassword, updateUser } from "@/lib/users";
import type { Role, User } from "@/lib/types";

interface BaseProps {
  roles: Role[];
  /** The currently logged-in user. Used to gate role choices for managers. */
  actor: User;
  onClose: () => void;
  onSaved: (user: User) => void;
}

type Props =
  | (BaseProps & { mode: "create" })
  | (BaseProps & { mode: "edit"; user: User });

export function UserModal(props: Props) {
  const { t } = useT();
  const isEdit = props.mode === "edit";
  const target = isEdit ? props.user : null;

  const [email, setEmail] = useState(target?.email ?? "");
  const [fullName, setFullName] = useState(target?.full_name ?? "");
  const [roleId, setRoleId] = useState<number>(
    target?.role.id ?? props.roles[0]?.id ?? 0,
  );
  const [isActive, setIsActive] = useState<boolean>(target?.is_active ?? true);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") props.onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [props]);

  const allowedRoles = props.roles.filter((r) => {
    if (props.actor.role.name === "manager" && r.name === "admin") return false;
    return true;
  });

  const editingSelf = isEdit && target!.id === props.actor.id;
  const editingAdminAsManager =
    isEdit && props.actor.role.name === "manager" && target!.role.name === "admin";

  if (editingAdminAsManager) {
    return (
      <Backdrop onClose={props.onClose}>
        <p className="text-sm text-red-600 dark:text-red-400">
          {t("users.managersCantEditAdmins")}
        </p>
        <FooterClose onClose={props.onClose} closeLabel={t("common.close")} />
      </Backdrop>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (props.mode === "create") {
        const created = await createUser({
          email,
          full_name: fullName.trim() || null,
          password,
          role_id: roleId,
          is_active: isActive,
        });
        props.onSaved(created);
        props.onClose();
      } else {
        const updated = await updateUser(target!.id, {
          full_name: fullName.trim() || null,
          role_id: roleId,
          is_active: isActive,
        });

        if (password.trim()) {
          const final = await resetUserPassword(updated.id, password);
          props.onSaved(final);
        } else {
          props.onSaved(updated);
        }
        props.onClose();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("users.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Backdrop onClose={props.onClose}>
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {isEdit ? t("users.modalEdit", { email: target!.email }) : t("users.modalNew")}
      </h2>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        {!isEdit && (
          <Field label={t("users.colEmail")}>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
              className={inputClass}
            />
          </Field>
        )}

        <Field label={t("users.fieldFullName")}>
          <input
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder={t("users.fieldFullNamePlaceholder")}
            className={inputClass}
          />
        </Field>

        <Field label={t("users.fieldRole")}>
          <select
            value={roleId}
            onChange={(e) => setRoleId(Number(e.target.value))}
            disabled={editingSelf}
            className={inputClass}
          >
            {allowedRoles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          {editingSelf && (
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              {t("users.cantChangeOwnRole")}
            </p>
          )}
        </Field>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isActive}
            disabled={editingSelf}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4"
          />
          <span className="font-medium text-neutral-700 dark:text-neutral-300">{t("users.fieldActive")}</span>
          {editingSelf && (
            <span className="text-xs text-neutral-500 dark:text-neutral-400">{t("users.cantDeactivateSelf")}</span>
          )}
        </label>

        <Field
          label={isEdit ? t("users.fieldPasswordReset") : t("users.fieldPassword")}
        >
          <input
            type="password"
            required={!isEdit}
            minLength={isEdit ? 0 : 8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={isEdit ? t("users.passwordPlaceholderEdit") : t("users.passwordPlaceholderNew")}
            autoComplete="new-password"
            className={inputClass}
          />
        </Field>

        {error && (
          <p className="rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>
        )}

        <div className="flex items-center justify-end gap-3 border-t border-neutral-200 dark:border-neutral-800 pt-4">
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-md border border-neutral-300 dark:border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {submitting
              ? t("common.saving")
              : isEdit
                ? t("users.saveChanges")
                : t("users.createUser")}
          </button>
        </div>
      </form>
    </Backdrop>
  );
}

const inputClass =
  "mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
      {label}
      {children}
    </label>
  );
}

function Backdrop({
  onClose,
  children,
}: {
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl bg-white dark:bg-neutral-900 p-6 shadow-xl"
      >
        {children}
      </div>
    </div>
  );
}

function FooterClose({ onClose, closeLabel }: { onClose: () => void; closeLabel: string }) {
  return (
    <div className="mt-5 flex justify-end">
      <button
        onClick={onClose}
        className="rounded-md border border-neutral-300 dark:border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
      >
        {closeLabel}
      </button>
    </div>
  );
}
