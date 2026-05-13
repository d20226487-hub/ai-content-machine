"use client";

import { FormEvent, useEffect, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { listEnabledProviders } from "@/lib/generate";
import {
  createPrompt,
  createTag,
  draftPromptWithAI,
  listTags,
} from "@/lib/prompts";
import type {
  Category,
  EnabledProvider,
  PromptDetail,
  Tag,
} from "@/lib/types";

import { Modal } from "./Modal";

type Mode = "manual" | "ai";

interface Props {
  categories: Category[];
  /** Pre-selected category. null = no folder. */
  defaultCategoryId: number | null;
  onClose: () => void;
  onCreated: (prompt: PromptDetail) => void;
}

export function NewPromptModal({
  categories,
  defaultCategoryId,
  onClose,
  onCreated,
}: Props) {
  const { t } = useT();
  const [mode, setMode] = useState<Mode>("manual");

  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(defaultCategoryId);
  const [content, setContent] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [tags, setTags] = useState<Tag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
  const [newTagName, setNewTagName] = useState("");

  const [aiDescription, setAiDescription] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiInfo, setAiInfo] = useState<string | null>(null);
  const [aiError, setAiError] = useState<unknown>(null);

  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [aiProviderCode, setAiProviderCode] = useState<string | null>(null);
  const [aiModel, setAiModel] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTags().then(setTags).catch(() => {});
    listEnabledProviders()
      .then((prv) => {
        setProviders(prv);
        const usable = prv.find((p) => p.has_api_key) ?? prv[0];
        if (usable) {
          setAiProviderCode(usable.code);
          setAiModel(usable.default_model);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!aiProviderCode) return;
    const p = providers.find((x) => x.code === aiProviderCode);
    setAiModel(p?.default_model ?? null);
  }, [aiProviderCode, providers]);

  const aiProvider = providers.find((p) => p.code === aiProviderCode);
  const noProviders = providers.length === 0;

  function toggleTag(id: number) {
    setSelectedTagIds((cur) =>
      cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id],
    );
  }

  async function onAddTag() {
    const tagName = newTagName.trim();
    if (!tagName) return;
    try {
      const tag = await createTag(tagName);
      setTags((cur) => (cur.find((t) => t.id === tag.id) ? cur : [...cur, tag]));
      setSelectedTagIds((cur) => (cur.includes(tag.id) ? cur : [...cur, tag.id]));
      setNewTagName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("newPrompt.failedAddTag"));
    }
  }

  async function onAiDraft() {
    setAiBusy(true);
    setAiInfo(null);
    setAiError(null);
    try {
      const result = await draftPromptWithAI(
        aiDescription,
        aiProviderCode ?? undefined,
        aiModel ?? undefined,
      );
      setContent(result.draft_content);
      setAiInfo(t("newPrompt.draftedWith", { provider: result.provider_used, model: result.model_used }));
      setMode("manual");
    } catch (err) {
      console.error("[Prompts] AI draft failed", err);
      setAiError(err);
    } finally {
      setAiBusy(false);
    }
  }

  async function doSave(): Promise<boolean> {
    setSubmitting(true);
    setError(null);
    try {
      const created = await createPrompt({
        name: name.trim(),
        category_id: categoryId,
        content,
        change_note: changeNote.trim() || null,
        tag_ids: selectedTagIds,
      });
      onCreated(created);
      onClose();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("newPrompt.failedCreate"));
      return false;
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await doSave();
  }

  // Dirty = the user has typed anything that would survive a discard.
  const dirty =
    name.trim().length > 0 ||
    content.length > 0 ||
    selectedTagIds.length > 0 ||
    changeNote.trim().length > 0 ||
    aiDescription.trim().length > 0;
  // Valid mirrors the Save button's enabled state: in Manual mode the
  // backend rejects empty name/content, so don't auto-save from
  // outside-click until both are filled.
  const valid =
    !submitting && mode === "manual" && name.trim().length > 0 && content.length > 0;

  return (
    <Modal
      onClose={onClose}
      size="max-w-2xl"
      dirty={dirty}
      valid={valid}
      onSaveAndClose={() => void doSave()}
    >
      <div className="flex items-start justify-between">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">{t("newPrompt.title")}</h2>
        <div className="flex rounded-md border border-neutral-200 dark:border-neutral-800 p-0.5 text-xs">
          <button
            onClick={() => setMode("manual")}
            className={
              "rounded px-3 py-1 font-medium " +
              (mode === "manual"
                ? "bg-neutral-900 text-white"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100")
            }
          >
            {t("newPrompt.modeManual")}
          </button>
          <button
            onClick={() => setMode("ai")}
            className={
              "rounded px-3 py-1 font-medium " +
              (mode === "ai"
                ? "bg-neutral-900 text-white"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100")
            }
          >
            {t("newPrompt.modeAi")}
          </button>
        </div>
      </div>

      {mode === "ai" && (
        <div className="mt-5 space-y-3 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 p-4">
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("newPrompt.aiDescribe")}
            <textarea
              rows={4}
              value={aiDescription}
              onChange={(e) => setAiDescription(e.target.value)}
              placeholder={t("newPrompt.aiDescribePlaceholder")}
              className="mt-1 block w-full rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500"
            />
          </label>

          {noProviders ? (
            <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
              {t("newPrompt.noProviderEnabled")}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("newPrompt.providerLabel")}
                <select
                  value={aiProviderCode ?? ""}
                  onChange={(e) => setAiProviderCode(e.target.value || null)}
                  className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
                >
                  {providers.map((p) => (
                    <option key={p.code} value={p.code} disabled={!p.has_api_key}>
                      {p.display_name}
                      {!p.has_api_key && ` ${t("newPrompt.providerNoApiKey")}`}
                    </option>
                  ))}
                </select>
                {aiProvider && !aiProvider.has_api_key && (
                  <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
                    {t("newPrompt.providerNoKeyHint")}
                  </p>
                )}
              </label>
              {aiProvider && (
                <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
                  {t("newPrompt.modelLabel")}
                  <select
                    value={aiModel ?? ""}
                    onChange={(e) => setAiModel(e.target.value || null)}
                    className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
                  >
                    {(aiProvider.available_models.length > 0
                      ? aiProvider.available_models
                      : aiProvider.default_model
                        ? [aiProvider.default_model]
                        : []
                    ).map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}

          {aiError != null && <ErrorPanel title={t("newPrompt.aiDraftFailed")} error={aiError} />}

          <div className="flex items-center justify-end">
            <button
              type="button"
              onClick={onAiDraft}
              disabled={aiBusy || noProviders || aiDescription.trim().length < 4}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
            >
              {aiBusy ? t("newPrompt.drafting") : t("newPrompt.draftButton")}
            </button>
          </div>
        </div>
      )}

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("newPrompt.fieldName")}>
            <input
              type="text"
              required
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
            rows={10}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={t("newPrompt.contentPlaceholder")}
            className={`${inputClass} font-mono text-xs`}
          />
          {aiInfo && (
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{aiInfo}</p>
          )}
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
                    ? "bg-neutral-900 text-white"
                    : "bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200 dark:hover:bg-neutral-700")
                }
              >
                {tag.name}
              </button>
            ))}
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
              className="rounded-md border border-neutral-300 dark:border-neutral-700 px-3 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800"
            >
              {t("common.add")}
            </button>
          </div>
        </Field>

        <Field label={t("newPrompt.fieldChangeNote")}>
          <input
            type="text"
            value={changeNote}
            onChange={(e) => setChangeNote(e.target.value)}
            placeholder={t("newPrompt.changeNotePlaceholder")}
            className={inputClass}
          />
        </Field>

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
            disabled={submitting || !name.trim() || !content.trim()}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200 disabled:opacity-60"
          >
            {submitting ? t("common.creating") : t("newPrompt.createPrompt")}
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
