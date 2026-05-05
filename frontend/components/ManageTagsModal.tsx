"use client";

import { FormEvent, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { createTag, deleteTag } from "@/lib/prompts";
import type { Tag } from "@/lib/types";

interface Props {
  tags: Tag[];
  onClose: () => void;
  /** Called whenever the tag list changes (add or delete). */
  onChanged: (tags: Tag[]) => void;
}

export function ManageTagsModal({ tags, onClose, onChanged }: Props) {
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setAdding(true);
    setError(null);
    try {
      const tag = await createTag(name);
      // createTag is idempotent server-side; only append if not already present.
      onChanged(tags.find((t) => t.id === tag.id) ? tags : [...tags, tag]);
      setNewName("");
    } catch (err) {
      console.error("[Tags] add failed", err);
      setError(err);
    } finally {
      setAdding(false);
    }
  }

  async function onDelete(tag: Tag) {
    if (
      !window.confirm(
        `Delete tag "${tag.name}"? It will be removed from any prompts that use it.`,
      )
    )
      return;
    try {
      await deleteTag(tag.id);
      onChanged(tags.filter((t) => t.id !== tag.id));
    } catch (err) {
      console.error("[Tags] delete failed", err);
      setError(err);
    }
  }

  const sorted = [...tags].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <Modal onClose={onClose} size="max-w-md">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        Manage tags
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        Tags are shared across all prompts. Deleting one removes it from every
        prompt that used it.
      </p>

      <form onSubmit={onAdd} className="mt-5 flex gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New tag name"
          className="flex-1 rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
        />
        <button
          type="submit"
          disabled={adding || !newName.trim()}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {adding ? "Adding…" : "Add"}
        </button>
      </form>

      {error != null && (
        <div className="mt-3">
          <ErrorPanel title="Failed" error={error} />
        </div>
      )}

      <div className="mt-5 max-h-80 overflow-y-auto rounded-md border border-neutral-200 dark:border-neutral-800">
        {sorted.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-neutral-500 dark:text-neutral-400">
            No tags yet. Add one above.
          </p>
        ) : (
          <ul className="divide-y divide-neutral-200 dark:divide-neutral-800">
            {sorted.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
              >
                <span className="truncate text-neutral-800 dark:text-neutral-200">
                  {t.name}
                </span>
                <button
                  onClick={() => void onDelete(t)}
                  className="shrink-0 text-xs font-medium text-red-600 hover:underline dark:text-red-400"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-5 flex justify-end">
        <button
          onClick={onClose}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          Close
        </button>
      </div>
    </Modal>
  );
}
