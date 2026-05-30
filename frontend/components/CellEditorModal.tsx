"use client";

import { useEffect, useState } from "react";

import { HtmlViewer } from "@/components/HtmlViewer";
import { Modal } from "@/components/Modal";
import { TranslationPanel } from "@/components/TranslationPanel";
import { translateCell } from "@/lib/brain";
import { useT } from "@/lib/i18n-context";
import type { CellTranslation } from "@/lib/types";

type Mode = "edit" | "preview";

/**
 * Translation context — set only for output cells with a saved value.
 * When provided, the modal renders a side-by-side "Translate" panel so
 * a colleague who doesn't know the source language can read the output
 * in their own language. Translations are view-only — never written
 * back into the cell's `value`.
 */
export interface TranslationContext {
  tableId: number;
  rowId: number;
  columnId: number;
  /** Last persisted translations (server returns this dict on table fetch). */
  initial: Record<string, CellTranslation> | null;
  /** Picker default — falls back to brain config when empty. */
  defaultTargetLanguage: string;
  /** Bubble fresh translations up so the table cache stays in sync. */
  onTranslated: (lang: string, entry: CellTranslation) => void;
}

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
  /** Provided only for output cells with a saved value. */
  translation?: TranslationContext;
}

export function CellEditorModal({
  title,
  initialValue,
  onSave,
  onClose,
  defaultMode = "edit",
  translation,
}: Props) {
  const { t } = useT();
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [draft, setDraft] = useState(initialValue);
  const [saving, setSaving] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

  useEffect(() => {
    setDraft(initialValue);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dirty = draft !== initialValue;
  // Translation is a read-side action — it doesn't make sense to offer
  // it while the user is actively editing the source. Gating on
  // mode==='preview' also keeps the top toolbar lean when the user is
  // typing into the textarea.
  const canTranslate =
    !!translation && draft.trim().length > 0 && mode === "preview";

  async function commit() {
    if (!dirty) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      await onSave(draft);
      onClose();
    } catch (err) {
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

  // Side-by-side panel widens the modal; otherwise the old size is fine.
  const modalSize = translateOpen ? "max-w-6xl" : "max-w-3xl";

  return (
    <Modal
      onClose={onClose}
      size={modalSize}
      dirty={dirty}
      valid={true}
      onSaveAndClose={() => void commit()}
    >
      {/* Top toolbar collapses when the translate panel is open — each
       *  HtmlViewer pane carries its own Preview / Raw / Copy / Open
       *  controls so a duplicate set here is just visual noise. The
       *  user closes the panel via the X next to the "Translation"
       *  label which then brings these tabs back. */}
      <div className="grid grid-cols-3 items-start gap-4">
        <h3 className="col-span-3 truncate text-sm font-medium text-neutral-900 dark:text-neutral-100 sm:col-span-1">
          {title}
        </h3>
        {!translateOpen && (
          <div className="col-span-3 flex shrink-0 items-center justify-center gap-2 sm:col-span-1">
            <div
              className="flex rounded-md border border-neutral-200 p-0.5 text-xs dark:border-neutral-700"
              data-testid="cell-mode-tabs"
            >
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
        )}
        {!translateOpen && (
          <div className="col-span-3 flex shrink-0 items-center justify-end sm:col-span-1">
            {canTranslate && (
              <button
                type="button"
                onClick={() => setTranslateOpen(true)}
                className="rounded-md border border-neutral-300 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
                data-testid="translate-toggle"
              >
                {t("translate.button")}
              </button>
            )}
          </div>
        )}
      </div>

      <div
        className={
          "mt-4 grid gap-4 " + (translateOpen ? "grid-cols-2" : "grid-cols-1")
        }
      >
        <div>
          {translateOpen && (
            // Pad the label row to match the right pane's form-control
            // row so the two iframes start at the same Y. Without this
            // the right row is taller and the text in the panes no
            // longer lines up.
            <div className="mb-2 flex min-h-[40px] items-center">
              <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                {t("translate.original")}
              </p>
            </div>
          )}
          {/* When the translate panel is open we force the original side to
           *  preview mode regardless of the Edit/Preview state — the
           *  HtmlViewer toolbar already exposes a Raw view, and editing the
           *  source while a translation hangs next to it is more confusing
           *  than helpful. Users who want to edit close the panel first. */}
          {mode === "edit" && !translateOpen ? (
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

        {translateOpen && translation && (
          <TranslationPanel
            initialTranslations={translation.initial}
            defaultTargetLanguage={translation.defaultTargetLanguage}
            autoRunOnOpen
            onClose={() => setTranslateOpen(false)}
            onTranslate={async (lang, force) => {
              const res = await translateCell(
                translation.tableId,
                translation.rowId,
                translation.columnId,
                lang,
                force,
              );
              return {
                text: res.text,
                provider_used: res.provider_used,
                model_used: res.model_used,
                translated_at: res.translated_at,
              };
            }}
            onTranslated={(lang, entry) =>
              translation.onTranslated(lang, entry)
            }
          />
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
