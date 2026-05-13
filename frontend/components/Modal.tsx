"use client";

import { useEffect, useRef, useState } from "react";

import { useT } from "@/lib/i18n-context";

interface Props {
  onClose: () => void;
  children: React.ReactNode;
  /** Tailwind max-w-* class. Default "max-w-lg". */
  size?: string;
  /**
   * Set to true when the modal contains unsaved edits. Without this, an
   * outside-click or Esc closes immediately (legacy behaviour).
   *
   * When dirty:
   *   - + valid + onSaveAndClose → outside-click saves and closes (no prompt).
   *   - otherwise → outside-click and Esc show an inline "discard?" strip
   *     at the top of the modal so a stray click can't lose work.
   */
  dirty?: boolean;
  /**
   * Set to true when the unsaved edits could be submitted right now. Drives
   * the save-on-outside-click branch above. Defaults to true so consumers
   * that don't track validity just get the "save aggressively" behaviour.
   */
  valid?: boolean;
  /**
   * Save callback for the dirty+valid outside-click path. Should run the
   * same submit logic the form's primary button does and is responsible for
   * eventually calling `onClose` itself.
   */
  onSaveAndClose?: () => void | Promise<void>;
}

export function Modal({
  onClose,
  children,
  size = "max-w-lg",
  dirty = false,
  valid = true,
  onSaveAndClose,
}: Props) {
  const { t } = useT();
  // Two-step discard for dirty modals: first dismiss arms the strip, the
  // user then confirms or cancels. Stops accidental clicks from nuking work.
  const [confirming, setConfirming] = useState(false);

  // Refs so the Esc handler always sees the latest props without us having
  // to rebind the listener on every render.
  const dirtyRef = useRef(dirty);
  const validRef = useRef(valid);
  const onSaveAndCloseRef = useRef(onSaveAndClose);
  const onCloseRef = useRef(onClose);
  dirtyRef.current = dirty;
  validRef.current = valid;
  onSaveAndCloseRef.current = onSaveAndClose;
  onCloseRef.current = onClose;

  function attemptDismiss(source: "outside" | "esc"): void {
    if (!dirtyRef.current) {
      onCloseRef.current();
      return;
    }
    if (
      source === "outside" &&
      validRef.current &&
      onSaveAndCloseRef.current
    ) {
      void onSaveAndCloseRef.current();
      return;
    }
    setConfirming(true);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") attemptDismiss("esc");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // attemptDismiss reads from refs, so it doesn't need to be in deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reset the confirm strip if the parent clears `dirty` (e.g. the user
  // saved via the primary button while the strip was visible).
  useEffect(() => {
    if (!dirty) setConfirming(false);
  }, [dirty]);

  return (
    <div
      onClick={() => attemptDismiss("outside")}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full ${size} rounded-xl bg-white dark:bg-neutral-900 p-6 shadow-xl`}
      >
        {confirming && (
          <div
            role="alert"
            className="mb-4 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
          >
            <span className="font-medium">{t("modal.unsavedConfirm")}</span>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded-md border border-amber-300 px-2 py-1 font-medium hover:bg-amber-100 dark:border-amber-700/60 dark:hover:bg-amber-900/40"
              >
                {t("modal.keepEditing")}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md bg-amber-600 px-2 py-1 font-medium text-white hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600"
              >
                {t("modal.discard")}
              </button>
            </div>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
