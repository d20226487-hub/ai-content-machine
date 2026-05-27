"use client";

import { useEffect, useState } from "react";

import { HtmlViewer } from "@/components/HtmlViewer";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";

interface Props {
  title: string;
  initialValue: string;
  onSave: (next: string) => void | Promise<void>;
  onClose: () => void;
  /** Which mode to land in when the modal opens. Output cells default
   *  to preview so the user can read the generated content first and
   *  flip to edit only if they want to tweak it. Input cells default
   *  to edit since previewing raw text is rarely useful. */
  defaultMode?: Mode;
}

type Mode = "edit" | "preview";

export function CellEditorModal({
  title,
  initialValue,
  onSave,
  onClose,
  defaultMode = "edit",
}: Props) {
  const { t } = useT();
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [draft, setDraft] = useState(initialValue);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(initialValue);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dirty = draft !== initialValue;

  async function commit() {
    if (!dirty) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
      // Close ourselves on success — historically the parent's onSave
      // also called setViewing(null), but if the parent's downstream
      // flush hangs or races during unmount, the button could stay
      // stuck on "Saving…" with no way out except closing the window.
      // Owning the close inside the modal is idempotent (parents that
      // also call onClose are no-ops the second time).
      onClose();
    } catch (err) {
      // Surface unexpected errors instead of silently swallowing them
      // so a stuck save at least shows something. The parent already
      // owns network-error reporting via its own UI; this is the
      // defense-in-depth path.
      console.error("[CellEditor] save failed", err);
    } finally {
      setSaving(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void commit();
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="max-w-3xl"
      dirty={dirty}
      valid={true}
      onSaveAndClose={() => void commit()}
    >
      <div className="flex items-start justify-between gap-4">
        <h3 className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
          {title}
        </h3>
        <div className="flex shrink-0 rounded-md border border-neutral-200 p-0.5 text-xs dark:border-neutral-700">
          <button
            type="button"
            onClick={() => setMode("edit")}
            className={
              "rounded px-3 py-1 font-medium " +
              (mode === "edit"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {t("cellEditor.edit")}
          </button>
          <button
            type="button"
            onClick={() => setMode("preview")}
            className={
              "rounded px-3 py-1 font-medium " +
              (mode === "preview"
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {t("cellEditor.preview")}
          </button>
        </div>
      </div>

      <div className="mt-4">
        {mode === "edit" ? (
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKey}
            placeholder={t("cellEditor.empty")}
            className="block h-[28rem] w-full rounded-md border border-neutral-300 bg-white p-3 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
          />
        ) : (
          <HtmlViewer content={draft} title="" height="h-[28rem]" />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-neutral-200 pt-4 dark:border-neutral-800">
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {dirty ? t("cellEditor.unsavedChanges") : t("cellEditor.noChanges")}
          <span className="ml-3 hidden sm:inline">
            <kbd className="rounded border border-neutral-300 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600 dark:border-neutral-700 dark:text-neutral-400">
              {typeof navigator !== "undefined" && /Mac/i.test(navigator.platform)
                ? "⌘"
                : "Ctrl"}
            </kbd>{" "}
            +{" "}
            <kbd className="rounded border border-neutral-300 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600 dark:border-neutral-700 dark:text-neutral-400">
              Enter
            </kbd>{" "}
            {t("cellEditor.toSave")}
          </span>
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={() => void commit()}
            disabled={saving || !dirty}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
