"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Pagination } from "@/components/Pagination";
import { updateSession } from "@/lib/createSession";
import {
  deleteSavedGeneration,
  getSavedGeneration,
  listSavedGenerations,
  renameSavedGeneration,
} from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import { markPendingNav } from "@/lib/pendingNav";
import type { SavedGenerationListItem } from "@/lib/types";

const PAGE_SIZE = 25;

export default function SavedGenerationsPage() {
  const { t } = useT();
  const router = useRouter();

  const [items, setItems] = useState<SavedGenerationListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Debounce the search so each keystroke doesn't refetch.
  useEffect(() => {
    const id = setTimeout(() => setQ(qInput), 350);
    return () => clearTimeout(id);
  }, [qInput]);

  // Any search change resets to page 1.
  useEffect(() => {
    setPage(1);
  }, [q]);

  const load = useCallback(() => {
    listSavedGenerations({ page, pageSize: PAGE_SIZE, q: q || undefined })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
        setError(null);
      })
      .catch((e) => {
        console.error("[Saved] list failed", e);
        setError(e);
      });
  }, [page, q]);
  useEffect(() => load(), [load]);

  async function onPick(id: number) {
    try {
      const s = await getSavedGeneration(id);
      // Loading a saved generation jumps straight to the output view — the
      // form snapshot is preserved so the user can still go Back to form.
      updateSession({
        form: {
          selectedPromptId: s.prompt_id,
          selectedPromptVersionNumber: s.prompt_version_number,
          selectedPromptName: s.prompt_name_snapshot,
          varValues: s.variables,
          providerCode: s.provider_code,
          model: s.model_used,
        },
        result: {
          text: s.output,
          rendered_prompt: s.rendered_prompt,
          provider_used: s.provider_code,
          model_used: s.model_used,
          finish_reason: s.finish_reason,
          missing_variables: [],
        },
        savedId: s.id,
        viewingSaved: s,
        localTranslations: {},
      });
      markPendingNav("/create/output");
      router.push("/create/output");
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
      // Refetch so pagination/total stay correct after the removal.
      load();
    } catch (e) {
      console.error("[Saved] delete failed", e);
      setError(e);
    }
  }

  const searching = q.trim().length > 0;

  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <div className="mb-4">
        <Link
          href="/create"
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("saved.backToCreate")}
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("saved.title")}
        </h1>
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("saved.onlyYours")}
        </p>
      </div>

      <div className="mt-4">
        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder={t("saved.searchPlaceholder")}
          className="w-full rounded-md border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </div>

      {error != null && (
        <div className="mt-4">
          <ErrorPanel title={t("common.failedToLoad")} error={error} />
        </div>
      )}

      {!items && !error && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      )}

      {items && items.length === 0 && (
        <div className="mt-6 rounded-lg border border-dashed border-neutral-300 bg-white p-8 text-center text-sm text-neutral-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-400">
          {searching ? t("saved.noMatches") : t("saved.empty")}
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <ul className="mt-5 divide-y divide-neutral-200 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
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
                        {g.prompt_version_number != null &&
                          ` · ${t("prompts.versionPrefix")}${g.prompt_version_number}`}
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
                      onClick={() => void onPick(g.id)}
                      className="font-medium text-neutral-700 hover:underline dark:text-neutral-300"
                    >
                      {t("saved.open")}
                    </button>
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
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onPage={setPage}
          />
        </>
      )}
    </main>
  );
}
