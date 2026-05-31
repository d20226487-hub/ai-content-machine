"use client";

import { useState } from "react";

import { useT } from "@/lib/i18n-context";

/**
 * Compact rename + delete actions for a tool "run" (find/replace, link check,
 * link fix, generation, publish). Uses prompt()/confirm() to stay tiny and
 * consistent with the rest of the app's destructive-action pattern. Safe to
 * drop inside a clickable <Link> row — clicks are stopped from bubbling.
 */
export function RunRowActions({
  name,
  onRename,
  onDelete,
  canDelete = true,
}: {
  name: string | null;
  onRename: (name: string | null) => Promise<void> | void;
  /** Omit to hide the delete action entirely. */
  onDelete?: () => Promise<void> | void;
  canDelete?: boolean;
}) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);

  async function rename(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const next = window.prompt(t("runs.renamePrompt"), name ?? "");
    if (next === null) return; // cancelled
    const trimmed = next.trim();
    setBusy(true);
    try {
      await onRename(trimmed || null);
    } finally {
      setBusy(false);
    }
  }

  async function del(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!onDelete) return;
    if (!window.confirm(t("runs.confirmDelete"))) return;
    setBusy(true);
    try {
      await onDelete();
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        onClick={rename}
        disabled={busy}
        title={t("runs.rename")}
        className="rounded px-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 disabled:opacity-50 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
      >
        ✏︎
      </button>
      {onDelete && canDelete && (
        <button
          type="button"
          onClick={del}
          disabled={busy}
          title={t("runs.delete")}
          className="rounded px-1 text-red-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 dark:hover:bg-red-950/40 dark:hover:text-red-300"
        >
          ✕
        </button>
      )}
    </span>
  );
}
