"use client";

import { useEffect, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { useT } from "@/lib/i18n-context";
import {
  deleteSavedGeneration,
  getSavedGeneration,
  listSavedGenerations,
  renameSavedGeneration,
} from "@/lib/generate";
import type { SavedGeneration, SavedGenerationListItem } from "@/lib/types";

interface Props {
  onClose: () => void;
  onLoad: (saved: SavedGeneration) => void;
}

export function SavedGenerationsModal({ onClose, onLoad }: Props) {
  const { t } = useT();
  const [items, setItems] = useState<SavedGenerationListItem[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    listSavedGenerations()
      .then(setItems)
      .catch((e) => {
        console.error("[Saved] list failed", e);
        setError(e);
      });
  }, []);

  async function onPick(id: number) {
    try {
      const full = await getSavedGeneration(id);
      onLoad(full);
      onClose();
    } catch (e) {
      console.error("[Saved] load failed", e);
      setError(e);
    }
  }

  async function onConfirmRename(id: number) {
    const name = renameValue.trim();
    if (!name) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await renameSavedGeneration(id, name);
      setItems((cur) => cur?.map((x) => (x.id === id ? updated : x)) ?? cur);
      setRenamingId(null);
    } catch (e) {
      console.error("[Saved] rename failed", e);
      setError(e);
    }
  }

  async function onDelete(id: number, name: string) {
    if (!window.confirm(t("saved.confirmDelete", { name }))) return;
    try {
      await deleteSavedGeneration(id);
      setItems((cur) => cur?.filter((x) => x.id !== id) ?? cur);
    } catch (e) {
      console.error("[Saved] delete failed", e);
      setError(e);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-3xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          {t("saved.title")}
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("saved.onlyYours")}
        </p>
      </div>

      {error != null && (
        <div className="mt-4">
          <ErrorPanel title={t("common.failedToLoad")} error={error} />
        </div>
      )}

      {!items && !error && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">{t("common.loading")}</p>
      )}

      {items && items.length === 0 && (
        <div className="mt-6 rounded-lg border border-dashed border-neutral-300 bg-white p-8 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-400">
          {t("saved.empty")}
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="mt-5 max-h-[60vh] divide-y divide-neutral-200 overflow-y-auto rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
          {items.map((g) => (
            <li
              key={g.id}
              className="flex items-center gap-4 p-3 hover:bg-neutral-50 dark:hover:bg-neutral-800"
            >
              <div className="min-w-0 flex-1">
                {renamingId === g.id ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void onConfirmRename(g.id);
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      className="flex-1 rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                    />
                    <button
                      onClick={() => void onConfirmRename(g.id)}
                      className="rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                    >
                      {t("common.save")}
                    </button>
                    <button
                      onClick={() => setRenamingId(null)}
                      className="rounded-md border border-neutral-300 px-3 py-1 text-xs font-medium text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
                    >
                      {t("common.cancel")}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => void onPick(g.id)}
                    className="block w-full text-left"
                  >
                    <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                      {g.name}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-neutral-500 dark:text-neutral-400">
                      {g.prompt_name_snapshot}
                      {g.prompt_version_number != null && ` · ${t("prompts.versionPrefix")}${g.prompt_version_number}`}
                      {" · "}
                      {g.provider_code}/{g.model_used}
                      {" · "}
                      {new Date(g.created_at).toLocaleString()}
                    </p>
                  </button>
                )}
              </div>
              {renamingId !== g.id && (
                <div className="flex shrink-0 items-center gap-3 text-xs">
                  <button
                    onClick={() => {
                      setRenamingId(g.id);
                      setRenameValue(g.name);
                    }}
                    className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                  >
                    {t("common.rename")}
                  </button>
                  <button
                    onClick={() => void onDelete(g.id, g.name)}
                    className="font-medium text-red-600 hover:underline dark:text-red-400"
                  >
                    {t("common.delete")}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-5 flex justify-end">
        <button
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          {t("common.close")}
        </button>
      </div>
    </Modal>
  );
}
