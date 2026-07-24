"use client";

import { useState } from "react";

import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { missingRequiredColumns } from "@/lib/autotool";
import { useT } from "@/lib/i18n-context";
import {
  autotoolCsvUrl,
  disableAutotool,
  enableAutotool,
} from "@/lib/library";

/** Downloadable import-file examples shown inside the Autotool dialog — trimmed
 *  3-row samples served from frontend/public/samples/autotool/. */
const AUTOTOOL_SAMPLES: {
  file: string;
  labelKey: "autotool.sampleSlots" | "autotool.sampleVendors";
}[] = [
  { file: "slots.csv", labelKey: "autotool.sampleSlots" },
  { file: "vendors.csv", labelKey: "autotool.sampleVendors" },
];

/**
 * Autotool toggle — the 3rd publishing mode. Sits next to the Generate button
 * in the bulk-table toolbar.
 *
 *   - Off: a single "Autotool" button. Clicking opens a dialog that explains
 *     the table will be exposed as a public, unauthenticated CSV and lets the
 *     operator uncheck columns that shouldn't be exposed.
 *   - On: "Copy CSV link" + "Columns (n/m)" (edit the included columns) +
 *     "Remove from Autotool" (guarded — the public link dies immediately).
 *
 * Column selection is per-table (null = all columns) and applies to the public
 * link AND the per-domain send files. State is kept locally (seeded from the
 * table) so buttons flip without a full reload; a refresh re-reads the truth.
 */
export function AutotoolButton({
  tableId,
  initialEnabled,
  initialToken,
  columns,
  initialColumnIds,
}: {
  tableId: number;
  initialEnabled: boolean;
  initialToken: string | null;
  columns: { id: number; name: string }[];
  /** null = all columns included. */
  initialColumnIds: number[] | null;
}) {
  const { t } = useT();
  const [enabled, setEnabled] = useState(initialEnabled);
  const [token, setToken] = useState<string | null>(initialToken);
  const [columnIds, setColumnIds] = useState<number[] | null>(initialColumnIds);
  const [dialog, setDialog] = useState<"enable" | "remove" | "columns" | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Working set for the column picker (shared by the enable + edit dialogs).
  const [checked, setChecked] = useState<Set<number>>(new Set());

  const includedCount = columnIds === null ? columns.length : columnIds.length;

  // Required-column guard for the picker. Validate the CHECKED names (what the
  // CSV will actually carry): a required role is "missing" if no checked column
  // matches it. Split into required columns the table lacks entirely (must be
  // added) vs ones that exist but are unchecked (must be re-checked) for a
  // clearer message. Mirrors the backend block in enable_autotool.
  const checkedNames = columns
    .filter((c) => checked.has(c.id))
    .map((c) => c.name);
  const missingRequired = missingRequiredColumns(checkedNames);
  const absentFromTable = missingRequiredColumns(columns.map((c) => c.name));
  const requiredNotInTable = missingRequired.filter((m) =>
    absentFromTable.includes(m),
  );
  const requiredUnchecked = missingRequired.filter(
    (m) => !absentFromTable.includes(m),
  );
  const saveDisabled = checked.size === 0 || missingRequired.length > 0;

  function openPicker(which: "enable" | "columns") {
    // Seed from the current selection; null = every column.
    setChecked(new Set(columnIds ?? columns.map((c) => c.id)));
    setError(null);
    setDialog(which);
  }

  function toggleCol(id: number) {
    setChecked((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // null when every column is checked, so a column added later is auto-included.
  function selectionForSave(): number[] | null {
    if (checked.size === 0 || checked.size >= columns.length) return null;
    return columns.filter((c) => checked.has(c.id)).map((c) => c.id);
  }

  async function submitSelection(closeOnly: boolean) {
    setBusy(true);
    setError(null);
    try {
      const s = await enableAutotool(tableId, selectionForSave());
      setEnabled(s.autotool_enabled);
      setToken(s.autotool_token);
      setColumnIds(s.column_ids ?? null);
      setDialog(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("autotool.failed"));
    } finally {
      setBusy(false);
    }
    void closeOnly;
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

  const columnPicker = (
    <div className="mt-3">
      <span className="block text-xs font-medium text-neutral-500 dark:text-neutral-400">
        {t("autotool.columnsLabel")}
      </span>
      <ul className="mt-1 max-h-52 space-y-0.5 overflow-y-auto rounded-md border border-neutral-200 p-2 dark:border-neutral-800">
        {columns.map((c) => (
          <li key={c.id}>
            <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-0.5 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800">
              <input
                type="checkbox"
                checked={checked.has(c.id)}
                onChange={() => toggleCol(c.id)}
                className="h-3.5 w-3.5"
              />
              <span className="truncate text-neutral-800 dark:text-neutral-200">
                {c.name}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {checked.size === 0 && (
        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
          {t("autotool.columnsNoneWarning")}
        </p>
      )}
      {checked.size > 0 && requiredNotInTable.length > 0 && (
        <p className="mt-1 text-xs text-red-700 dark:text-red-300">
          {t("autotool.requiredMissingTable", {
            cols: requiredNotInTable.join(", "),
          })}
        </p>
      )}
      {checked.size > 0 && requiredUnchecked.length > 0 && (
        <p className="mt-1 text-xs text-red-700 dark:text-red-300">
          {t("autotool.requiredUnchecked", {
            cols: requiredUnchecked.join(", "),
          })}
        </p>
      )}
    </div>
  );

  // Downloadable example import files (slots / vendors) so an operator can see
  // the exact column names + content format Autotool expects.
  const sampleLinks = (
    <div className="mt-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
      <span className="block text-xs font-medium text-neutral-500 dark:text-neutral-400">
        {t("autotool.samplesLabel")}
      </span>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
        {AUTOTOOL_SAMPLES.map((s) => (
          <a
            key={s.file}
            href={`/samples/autotool/${s.file}`}
            download
            className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {t(s.labelKey)}
          </a>
        ))}
      </div>
    </div>
  );

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
            onClick={() => openPicker("columns")}
            className="rounded-md border border-neutral-300 px-2 py-1 font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            title={t("autotool.columnsHint")}
          >
            {t("autotool.columnsBtn", {
              n: includedCount,
              total: columns.length,
            })}
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
          onClick={() => openPicker("enable")}
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
          confirmDisabled={saveDisabled}
          busy={busy}
          error={error}
          onCancel={closeDialog}
          onConfirm={() => void submitSelection(false)}
          extra={
            <>
              {columnPicker}
              {sampleLinks}
            </>
          }
        />
      )}

      {dialog === "columns" && (
        <ConfirmDialog
          title={t("autotool.columnsTitle")}
          body={t("autotool.columnsBody")}
          confirmLabel={t("autotool.columnsSave")}
          confirmTone="primary"
          confirmDisabled={saveDisabled}
          busy={busy}
          error={error}
          onCancel={closeDialog}
          onConfirm={() => void submitSelection(true)}
          extra={
            <>
              {columnPicker}
              {sampleLinks}
            </>
          }
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
  confirmDisabled,
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
  confirmDisabled?: boolean;
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
          disabled={busy || confirmDisabled}
          className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${confirmClass}`}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
