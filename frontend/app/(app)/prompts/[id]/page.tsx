"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EditPromptModal } from "@/components/EditPromptModal";
import { TranslationPanel } from "@/components/TranslationPanel";
import { ApiError } from "@/lib/api";
import { getBrainPrompts, translatePromptVersion } from "@/lib/brain";
import { useT } from "@/lib/i18n-context";
import {
  deletePrompt,
  editVersionNote,
  getPrompt,
  getPromptVersion,
  listCategories,
  listTags,
  revertPrompt,
} from "@/lib/prompts";
import type {
  Category,
  CellTranslation,
  PromptDetail,
  Tag,
} from "@/lib/types";

export default function PromptDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { t } = useT();
  const id = Number(params.id);

  const [prompt, setPrompt] = useState<PromptDetail | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const [versionContents, setVersionContents] = useState<Record<number, string>>({});
  const [openVersions, setOpenVersions] = useState<Set<number>>(new Set());

  const [editingNote, setEditingNote] = useState<number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  const VERSIONS_PER_PAGE = 20;
  const [versionPage, setVersionPage] = useState(1);

  // Translation panel for the current-version content. Memoized on
  // the server via /prompts/{id}/versions/{vnum}/translate, so re-opens
  // are free. Versions are immutable, so the cache lives forever per
  // (prompt_id, version_number) tuple.
  const [translateOpen, setTranslateOpen] = useState(false);
  const [translateDefaultLang, setTranslateDefaultLang] = useState("ru");

  useEffect(() => {
    let ignored = false;
    getBrainPrompts()
      .then((b) => {
        if (!ignored) {
          setTranslateDefaultLang(
            (b.translate.default_target_language || "ru").toLowerCase(),
          );
        }
      })
      .catch(() => {
        /* keep 'ru' fallback */
      });
    return () => {
      ignored = true;
    };
  }, []);

  // Switching to a different prompt closes any open translation panel
  // so we don't show one prompt's translation against another's source.
  useEffect(() => {
    setTranslateOpen(false);
  }, [prompt?.id, prompt?.current_version?.version_number]);

  async function commitNote(versionNumber: number) {
    if (!prompt) return;
    setSavingNote(true);
    try {
      const next = await editVersionNote(
        prompt.id,
        versionNumber,
        noteDraft.trim() || null,
      );
      setPrompt(next);
      setEditingNote(null);
    } catch (err) {
      console.error("[Prompt] note save failed", err);
      alert(t("promptDetail.noteSaveFailed"));
    } finally {
      setSavingNote(false);
    }
  }

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    let ignored = false;
    getPrompt(id)
      .then((p) => {
        if (!ignored) setPrompt(p);
      })
      .catch((err) => {
        if (ignored) return;
        setError(err instanceof ApiError ? err.message : t("common.failedToLoad"));
      });
    Promise.all([listCategories(), listTags()]).then(([cs, ts]) => {
      if (ignored) return;
      setCategories(cs);
      setTags(ts);
    });
    return () => {
      ignored = true;
    };
  }, [id, t]);

  if (error) {
    return (
      <main className="mx-auto max-w-3xl p-10">
        <Link href="/prompts" className="text-sm text-neutral-500 dark:text-neutral-400 hover:underline">
          {t("promptDetail.back")}
        </Link>
        <p className="mt-6 rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </p>
      </main>
    );
  }

  if (!prompt) {
    return (
      <main className="mx-auto max-w-3xl p-10 text-sm text-neutral-500 dark:text-neutral-400">
        {t("common.loading")}
      </main>
    );
  }

  const currentVN = prompt.current_version?.version_number ?? 0;

  async function toggleVersion(vn: number) {
    setOpenVersions((cur) => {
      const next = new Set(cur);
      if (next.has(vn)) {
        next.delete(vn);
      } else {
        next.add(vn);
      }
      return next;
    });
    if (versionContents[vn] === undefined && vn !== currentVN) {
      try {
        const detail = await getPromptVersion(prompt!.id, vn);
        setVersionContents((cur) => ({
          ...cur,
          [vn]: detail.current_version?.content ?? "",
        }));
      } catch {
        setVersionContents((cur) => ({ ...cur, [vn]: t("common.failedToLoad") }));
      }
    }
  }

  async function onRevert(vn: number) {
    if (!window.confirm(t("promptDetail.confirmRevert", { n: vn }))) return;
    try {
      const next = await revertPrompt(prompt!.id, vn);
      setPrompt(next);
      setVersionContents({});
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("promptDetail.revertFailed"));
    }
  }

  async function onDelete() {
    if (!window.confirm(t("promptDetail.confirmDelete", { name: prompt!.name }))) return;
    try {
      await deletePrompt(prompt!.id);
      router.replace("/prompts");
    } catch (err) {
      alert(err instanceof ApiError ? err.message : t("common.deleteFailed"));
    }
  }

  const folderName =
    prompt.category_id != null
      ? categories.find((c) => c.id === prompt.category_id)?.name
      : null;

  return (
    <main className="mx-auto max-w-4xl p-10">
      <Link href="/prompts" className="text-sm text-neutral-500 dark:text-neutral-400 hover:underline">
        {t("promptDetail.back")}
      </Link>

      <div className="mt-4 flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
            {prompt.name}
          </h1>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {folderName ? t("promptDetail.folderLabel", { name: folderName }) : t("promptDetail.noFolder")}
            {" · "}{t("prompts.versionPrefix")}{currentVN}
            {" · "}{t("promptDetail.updated", { time: new Date(prompt.updated_at).toLocaleString() })}
          </p>
          <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
            {t("promptDetail.createdBy")}{" "}
            <span className="font-medium text-neutral-700 dark:text-neutral-300">
              {prompt.created_by_name ?? prompt.created_by_email ?? t("common.unknown")}
            </span>{" "}
            {t("promptDetail.createdOn", { date: new Date(prompt.created_at).toLocaleDateString() })}
          </p>
          {prompt.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {prompt.tags.map((tag) => (
                <span
                  key={tag.id}
                  className="rounded-full bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 text-[10px] font-medium text-neutral-700 dark:text-neutral-300"
                >
                  {tag.name}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          <Link
            href={`/prompts/${prompt.id}/test`}
            title={t("promptDetail.testHint")}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {t("promptDetail.test")}
          </Link>
          <button
            onClick={() => setEditing(true)}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:hover:bg-neutral-200"
          >
            {t("common.edit")}
          </button>
          <button
            onClick={onDelete}
            className="rounded-md border border-neutral-300 dark:border-neutral-700 px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40"
          >
            {t("common.delete")}
          </button>
        </div>
      </div>

      {/* Current content */}
      <section className="mt-6 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">{t("promptDetail.currentContent")}</h2>
          <div className="flex items-center gap-3">
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {t("prompts.versionPrefix")}
              {currentVN}
            </span>
            {prompt.current_version?.content &&
              prompt.current_version.content.trim().length > 0 &&
              !translateOpen && (
                <button
                  type="button"
                  onClick={() => setTranslateOpen(true)}
                  className="rounded-md border border-neutral-300 px-2 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                  data-testid="prompt-translate-toggle"
                >
                  {t("translate.button")}
                </button>
              )}
          </div>
        </div>
        {translateOpen && prompt.current_version ? (
          <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-2 flex min-h-[40px] items-center">
                <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {t("translate.original")}
                </p>
              </div>
              <pre className="h-[28rem] overflow-auto whitespace-pre-wrap break-words rounded-md bg-neutral-50 dark:bg-neutral-950 p-4 font-mono text-xs text-neutral-800 dark:text-neutral-200">
                {prompt.current_version.content}
              </pre>
            </div>
            <TranslationPanel
              initialTranslations={prompt.current_version.translations ?? null}
              defaultTargetLanguage={translateDefaultLang}
              autoRunOnOpen
              onClose={() => setTranslateOpen(false)}
              // Prompt templates are plain text — Preview/Raw and the
              // Open-in-window button add no value. Trim the toolbar
              // to just Copy.
              compact
              onTranslate={async (lang, force) => {
                const res = await translatePromptVersion(
                  prompt.id,
                  prompt.current_version!.version_number,
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
              onTranslated={(lang, entry) => {
                if (!prompt.current_version) return;
                setPrompt({
                  ...prompt,
                  current_version: {
                    ...prompt.current_version,
                    translations: {
                      ...(prompt.current_version.translations ?? {}),
                      [lang]: entry,
                    },
                  },
                });
              }}
            />
          </div>
        ) : (
          <pre className="mt-3 whitespace-pre-wrap break-words rounded-md bg-neutral-50 dark:bg-neutral-950 p-4 font-mono text-xs text-neutral-800 dark:text-neutral-200">
            {prompt.current_version?.content ?? t("common.empty")}
          </pre>
        )}

        {prompt.variables.length > 0 && (
          <div className="mt-4">
            <h3 className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
              {t("promptDetail.variables")}
            </h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {prompt.variables.map((v) => (
                <code
                  key={v}
                  className="rounded bg-neutral-100 dark:bg-neutral-800 px-2 py-0.5 text-xs text-neutral-800 dark:text-neutral-200"
                >
                  {`{{${v}}}`}
                </code>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Version history */}
      <section className="mt-6">
        <h2 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("promptDetail.versionHistory", { count: prompt.versions.length })}
        </h2>
        {(() => {
          const totalVersionPages = Math.max(
            1,
            Math.ceil(prompt.versions.length / VERSIONS_PER_PAGE),
          );
          const safePage = Math.min(versionPage, totalVersionPages);
          const start = (safePage - 1) * VERSIONS_PER_PAGE;
          const visibleVersions = prompt.versions.slice(
            start,
            start + VERSIONS_PER_PAGE,
          );
          return (
            <>
        <ul className="mt-3 space-y-2">
          {visibleVersions.map((v) => {
            const isCurrent = v.version_number === currentVN;
            const open = openVersions.has(v.version_number);
            const content =
              v.version_number === currentVN
                ? prompt.current_version?.content ?? ""
                : versionContents[v.version_number];
            return (
              <li
                key={v.id}
                className="overflow-hidden rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900"
              >
                <div
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("[data-no-toggle]"))
                      return;
                    toggleVersion(v.version_number);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      void toggleVersion(v.version_number);
                    }
                  }}
                  className="flex w-full cursor-pointer items-center justify-between gap-4 px-4 py-3 text-left hover:bg-neutral-50 dark:hover:bg-neutral-800"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                      {t("prompts.versionPrefix")}{v.version_number}
                      {isCurrent && (
                        <span className="ml-2 rounded-full bg-green-100 dark:bg-green-900/50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-green-700 dark:text-green-300">
                          {t("promptDetail.versionCurrent")}
                        </span>
                      )}
                      <span className="ml-2 text-xs font-normal text-neutral-500 dark:text-neutral-400">
                        {t("promptDetail.versionBy", { name: v.created_by_name ?? v.created_by_email ?? t("common.unknown") })}
                      </span>
                    </p>
                    {editingNote === v.version_number ? (
                      <div data-no-toggle className="mt-1 flex items-center gap-2">
                        <input
                          type="text"
                          autoFocus
                          value={noteDraft}
                          onChange={(e) => setNoteDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void commitNote(v.version_number);
                            }
                            if (e.key === "Escape") setEditingNote(null);
                          }}
                          placeholder={t("promptDetail.noteFor")}
                          className="flex-1 rounded-md border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                        />
                        <button
                          onClick={() => void commitNote(v.version_number)}
                          disabled={savingNote}
                          className="rounded-md bg-neutral-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
                        >
                          {savingNote ? t("common.saving") : t("common.save")}
                        </button>
                        <button
                          onClick={() => setEditingNote(null)}
                          className="rounded-md border border-neutral-300 px-2 py-1 text-xs text-neutral-700 dark:border-neutral-700 dark:text-neutral-300"
                        >
                          {t("common.cancel")}
                        </button>
                      </div>
                    ) : (
                      <p className="mt-0.5 truncate text-xs text-neutral-500 dark:text-neutral-400">
                        {v.change_note || <span className="italic">{t("promptDetail.noteEmpty")}</span>}
                        <button
                          data-no-toggle
                          onClick={(e) => {
                            e.stopPropagation();
                            setNoteDraft(v.change_note ?? "");
                            setEditingNote(v.version_number);
                          }}
                          className="ml-2 underline hover:text-neutral-900 dark:hover:text-neutral-100"
                        >
                          {v.change_note ? t("promptDetail.noteEdit") : t("promptDetail.noteAdd")}
                        </button>
                      </p>
                    )}
                  </div>
                  <div className="shrink-0 text-right text-xs text-neutral-500 dark:text-neutral-400">
                    <p>{new Date(v.created_at).toLocaleString()}</p>
                    {!isCurrent && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void onRevert(v.version_number);
                        }}
                        className="mt-1 font-medium text-neutral-700 dark:text-neutral-300 hover:text-neutral-900 dark:hover:text-neutral-100 hover:underline"
                      >
                        {t("promptDetail.revert")}
                      </button>
                    )}
                  </div>
                </div>
                {open && (
                  <pre className="whitespace-pre-wrap break-words border-t border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 p-4 font-mono text-xs text-neutral-800 dark:text-neutral-200">
                    {content ?? t("common.loading")}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
        {totalVersionPages > 1 && (
          <div className="mt-3 flex items-center justify-between text-xs text-neutral-600 dark:text-neutral-400">
            <span>
              {t("common.showingRange", {
                from: start + 1,
                to: start + visibleVersions.length,
                total: prompt.versions.length,
              })}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setVersionPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                className="rounded-md border border-neutral-300 px-2.5 py-1 disabled:opacity-50 dark:border-neutral-700"
              >
                {t("common.previous")}
              </button>
              <span className="px-1 py-1">
                {safePage} / {totalVersionPages}
              </span>
              <button
                onClick={() =>
                  setVersionPage((p) => Math.min(totalVersionPages, p + 1))
                }
                disabled={safePage >= totalVersionPages}
                className="rounded-md border border-neutral-300 px-2.5 py-1 disabled:opacity-50 dark:border-neutral-700"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        )}
            </>
          );
        })()}
      </section>

      {editing && (
        <EditPromptModal
          prompt={prompt}
          categories={categories}
          tags={tags}
          onClose={() => setEditing(false)}
          onSaved={(p) => {
            setPrompt(p);
            setVersionContents({});
            setOpenVersions(new Set());
          }}
        />
      )}
    </main>
  );
}
