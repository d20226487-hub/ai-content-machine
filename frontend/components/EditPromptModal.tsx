"use client";

import { FormEvent, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { createPromptVersion, createTag, updatePromptMeta } from "@/lib/prompts";
import type { Category, PromptDetail, Tag } from "@/lib/types";

import { Modal } from "./Modal";

interface Props {
  prompt: PromptDetail;
  categories: Category[];
  tags: Tag[];
  onClose: () => void;
  onSaved: (next: PromptDetail) => void;
  onTagsChanged?: (tags: Tag[]) => void;
}

export function EditPromptModal({
  prompt,
  categories,
  tags: tagsProp,
  onClose,
  onSaved,
  onTagsChanged,
}: Props) {
  const { t } = useT();
  const [name, setName] = useState(prompt.name);
  const [categoryId, setCategoryId] = useState<number | null>(prompt.category_id);
  const [content, setContent] = useState(prompt.current_version?.content ?? "");
  const [changeNote, setChangeNote] = useState("");
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>(
    prompt.tags.map((t) => t.id),
  );

  const [tags, setTags] = useState<Tag[]>(tagsProp);
  const [newTagName, setNewTagName] = useState("");
  const [addingTag, setAddingTag] = useState(false);

  async function onAddTag() {
    const tagName = newTagName.trim();
    if (!tagName) return;
    setAddingTag(true);
    try {
      const tag = await createTag(tagName);
      setTags((cur) => {
        const next = cur.find((x) => x.id === tag.id) ? cur : [...cur, tag];
        onTagsChanged?.(next);
        return next;
      });
      setSelectedTagIds((cur) => (cur.includes(tag.id) ? cur : [...cur, tag.id]));
      setNewTagName("");
    } catch (err) {
      console.error("[EditPrompt] add tag failed", err);
    } finally {
      setAddingTag(false);
    }
  }

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const contentChanged = content !== (prompt.current_version?.content ?? "");
  const metaChanged =
    name.trim() !== prompt.name ||
    categoryId !== prompt.category_id ||
    !arraysEqual(
      selectedTagIds.slice().sort(),
      prompt.tags.map((t) => t.id).sort(),
    );

  function toggleTag(id: number) {
    setSelectedTagIds((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!contentChanged && !metaChanged) {
      onClose();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      let updated: PromptDetail = prompt;

      if (metaChanged) {
        updated = await updatePromptMeta(prompt.id, {
          name: name.trim(),
          category_id: categoryId,
          tag_ids: selectedTagIds,
        });
      }

      if (contentChanged) {
        updated = await createPromptVersion(
          prompt.id,
          content,
          changeNote.trim() || null,
        );
      }

      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("users.saveFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-2xl">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{t("editPrompt.title")}</h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("editPrompt.subtitle")}
      </p>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("newPrompt.fieldName")}>
            <input
              required
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
            />
          </Field>
          <Field label={t("newPrompt.fieldFolder")}>
            <select
              value={categoryId ?? ""}
              onChange={(e) =>
                setCategoryId(e.target.value === "" ? null : Number(e.target.value))
              }
              className={inputClass}
            >
              <option value="">{t("newPrompt.folderNone")}</option>
              {categories
                .slice()
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          </Field>
        </div>

        <Field label={t("newPrompt.fieldContent")}>
          <textarea
            required
            rows={12}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className={`${inputClass} font-mono text-xs`}
          />
        </Field>

        <Field label={t("newPrompt.fieldTags")}>
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <button
                type="button"
                key={tag.id}
                onClick={() => toggleTag(tag.id)}
                className={
                  "rounded-full px-3 py-1 text-xs font-medium " +
                  (selectedTagIds.includes(tag.id)
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700")
                }
              >
                {tag.name}
              </button>
            ))}
            {tags.length === 0 && (
              <span className="text-xs text-neutral-400 dark:text-neutral-500">{t("editPrompt.noTags")}</span>
            )}
          </div>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={newTagName}
              onChange={(e) => setNewTagName(e.target.value)}
              placeholder={t("newPrompt.addTagPlaceholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void onAddTag();
                }
              }}
              className={`${inputClass} flex-1`}
            />
            <button
              type="button"
              onClick={onAddTag}
              disabled={addingTag || !newTagName.trim()}
              className="rounded-md border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              {addingTag ? t("common.adding") : t("common.add")}
            </button>
          </div>
        </Field>

        {contentChanged && (
          <Field label={t("editPrompt.fieldChangeNote")}>
            <input
              type="text"
              value={changeNote}
              onChange={(e) => setChangeNote(e.target.value)}
              placeholder={t("editPrompt.changeNotePlaceholder")}
              className={inputClass}
            />
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              {t("editPrompt.changeNoteFootnote")}
            </p>
          </Field>
        )}

        {error && (
          <p className="rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">{error}</p>
        )}

        <div className="flex items-center justify-end gap-3 border-t border-neutral-200 dark:border-neutral-800 pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-neutral-300 dark:border-neutral-700 px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={submitting || (!contentChanged && !metaChanged)}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {submitting
              ? t("common.saving")
              : contentChanged
                ? t("editPrompt.saveAsNewVersion")
                : t("users.saveChanges")}
          </button>
        </div>
      </form>
    </Modal>
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

function arraysEqual<T>(a: T[], b: T[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
