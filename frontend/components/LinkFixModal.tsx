"use client";

import { useEffect, useState } from "react";

import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import { getLinkFixDefaultPrompt } from "@/lib/linkFix";
import type { BulkColumn } from "@/lib/types";

/** Where corrected content should be written. */
export type FixTargetChoice =
  | { kind: "new"; name: string }
  | { kind: "existing"; columnId: number }
  | { kind: "overwrite" };

interface Props {
  /** Table the fix runs on — used to fetch the previously-used prompt. */
  tableId: number;
  columns: BulkColumn[];
  /** How many cells will be fixed (for the confirm copy). */
  count: number;
  busy: boolean;
  onClose: () => void;
  onConfirm: (target: FixTargetChoice, prompt: string) => void;
}

const NEW_DEFAULT = "Fixed links";

export function LinkFixModal({
  tableId,
  columns,
  count,
  busy,
  onClose,
  onConfirm,
}: Props) {
  const { t } = useT();
  // "new" | "overwrite" | "<columnId>"
  const [mode, setMode] = useState<string>("new");
  const [newName, setNewName] = useState(NEW_DEFAULT);
  // Correction prompt — defaults to the previously-used job prompt (or the
  // Brain default), and the user can edit it before running.
  const [prompt, setPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    getLinkFixDefaultPrompt(tableId)
      .then((r) => {
        if (alive) setPrompt(r.prompt);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setPromptLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tableId]);

  function confirm() {
    const p = prompt.trim();
    if (mode === "new") {
      const name = newName.trim() || NEW_DEFAULT;
      onConfirm({ kind: "new", name }, p);
    } else if (mode === "overwrite") {
      onConfirm({ kind: "overwrite" }, p);
    } else {
      onConfirm({ kind: "existing", columnId: Number(mode) }, p);
    }
  }

  const newNameInvalid = mode === "new" && newName.trim().length === 0;

  return (
    <Modal onClose={onClose} size="max-w-lg">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("linkFix.modalTitle")}
      </h2>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {t("linkFix.modalSubtitle", { n: count })}
      </p>

      <label className="mt-5 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("linkFix.targetLabel")}
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        >
          <option value="new">{t("linkFix.targetNew")}</option>
          {columns.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {t("linkFix.targetExisting", { name: c.name })}
            </option>
          ))}
          <option value="overwrite">{t("linkFix.targetOverwrite")}</option>
        </select>
      </label>

      {mode === "new" && (
        <label className="mt-3 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("linkFix.newColumnName")}
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={120}
            className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>
      )}

      {mode === "overwrite" && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-400/10 dark:text-amber-200">
          {t("linkFix.overwriteWarn")}
        </p>
      )}

      <label className="mt-4 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
        {t("linkFix.promptLabel")}
        <span className="block text-xs font-normal text-neutral-400 dark:text-neutral-500">
          {t("linkFix.promptHint")}
        </span>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={7}
          disabled={promptLoading}
          placeholder={promptLoading ? t("common.loading") : undefined}
          className="mt-1 block max-h-72 w-full rounded-md border border-neutral-300 px-3 py-2 text-xs leading-relaxed dark:border-neutral-700 dark:bg-neutral-900"
        />
      </label>

      <div className="mt-6 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          {t("common.cancel")}
        </button>
        <button
          type="button"
          onClick={confirm}
          disabled={busy || newNameInvalid || promptLoading}
          className="rounded-md bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60"
        >
          {busy ? t("common.loading") : t("linkFix.startFix")}
        </button>
      </div>
    </Modal>
  );
}
