"use client";

import { useState } from "react";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  autotoolCsvUrl,
  disableAutotool,
  enableAutotool,
} from "@/lib/library";

/**
 * Autotool toggle — the 3rd publishing mode. Sits next to the Generate button
 * in the bulk-table toolbar.
 *
 *   - Off: a single "Autotool" button. Clicking opens a confirm popup that
 *     explains the table will be exposed as a public, unauthenticated CSV.
 *   - On: a "Copy CSV link" affordance + a "Remove from Autotool" button.
 *     Removing is guarded by a confirm popup explaining the public link will
 *     be invalidated immediately.
 *
 * State is kept locally (seeded from the table) so the button flips without a
 * full table reload; a page refresh re-reads the authoritative value.
 */
export function AutotoolButton({
  tableId,
  initialEnabled,
  initialToken,
}: {
  tableId: number;
  initialEnabled: boolean;
  initialToken: string | null;
}) {
  const { t } = useT();
  const [enabled, setEnabled] = useState(initialEnabled);
  const [token, setToken] = useState<string | null>(initialToken);
  const [dialog, setDialog] = useState<"enable" | "remove" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function confirmEnable() {
    setBusy(true);
    setError(null);
    try {
      const s = await enableAutotool(tableId);
      setEnabled(s.autotool_enabled);
      setToken(s.autotool_token);
      setDialog(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("autotool.failed"));
    } finally {
      setBusy(false);
    }
  }

  async function confirmRemove() {
    setBusy(true);
    setError(null);
    try {
      const s = await disableAutotool(tableId);
      setEnabled(s.autotool_enabled);
      setToken(s.autotool_token);
      setDialog(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("autotool.failed"));
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(autotoolCsvUrl(token));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  function closeDialog() {
    if (busy) return;
    setDialog(null);
    setError(null);
  }

  return (
    <>
      {enabled ? (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => void copyLink()}
            className="rounded-md border border-emerald-300 px-2 py-1 font-medium text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
            title={autotoolCsvUrl(token ?? "")}
          >
            {copied ? t("autotool.copied") : t("autotool.copyLink")}
          </button>
          <button
            type="button"
            onClick={() => setDialog("remove")}
            className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            title={t("autotool.enabledHint")}
          >
            {t("autotool.remove")}
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setDialog("enable")}
          className="rounded-md border border-neutral-300 px-3 py-1 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          title={t("autotool.disabledHint")}
        >
          {t("autotool.button")}
        </button>
      )}

      {dialog === "enable" && (
        <ConfirmDialog
          title={t("autotool.enableTitle")}
          body={t("autotool.enableBody")}
          confirmLabel={t("autotool.enableConfirm")}
          confirmTone="primary"
          busy={busy}
          error={error}
          onCancel={closeDialog}
          onConfirm={() => void confirmEnable()}
        />
      )}

      {dialog === "remove" && (
        <ConfirmDialog
          title={t("autotool.removeTitle")}
          body={t("autotool.removeBody")}
          confirmLabel={t("autotool.removeConfirm")}
          confirmTone="danger"
          busy={busy}
          error={error}
          onCancel={closeDialog}
          onConfirm={() => void confirmRemove()}
          extra={
            token ? (
              <div className="mt-3">
                <span className="block text-xs font-medium text-neutral-500 dark:text-neutral-400">
                  {t("autotool.linkLabel")}
                </span>
                <code className="mt-1 block break-all rounded-md bg-neutral-100 px-2 py-1 text-xs text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                  {autotoolCsvUrl(token)}
                </code>
              </div>
            ) : null
          }
        />
      )}
    </>
  );
}

function ConfirmDialog({
  title,
  body,
  confirmLabel,
  confirmTone,
  busy,
  error,
  onCancel,
  onConfirm,
  extra,
}: {
  title: string;
  body: string;
  confirmLabel: string;
  confirmTone: "primary" | "danger";
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
  extra?: React.ReactNode;
}) {
  const { t } = useT();
  const confirmClass =
    confirmTone === "danger"
      ? "bg-red-600 hover:bg-red-700 text-white"
      : "bg-neutral-900 hover:bg-neutral-800 text-white dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200";
  return (
    <Modal onClose={onCancel} size="max-w-md">
      <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
        {title}
      </h3>
      <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">{body}</p>
      {extra}
      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("autotool.cancel")}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${confirmClass}`}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
