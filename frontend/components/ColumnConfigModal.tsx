"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { ErrorPanel } from "@/components/ErrorPanel";
import { Modal } from "@/components/Modal";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { listEnabledProviders, renderPrompt } from "@/lib/generate";
import { updateColumn } from "@/lib/library";
import { getPrompt, listCategories, listPrompts } from "@/lib/prompts";
import type {
  BulkColumn,
  BulkTable,
  Category,
  EnabledProvider,
  PromptDetail,
  PromptListItem,
} from "@/lib/types";

interface Props {
  table: BulkTable;
  column: BulkColumn;
  onClose: () => void;
  onSaved: (col: BulkColumn) => void;
}

/**
 * Configures an output column: pick a prompt, then map each prompt variable
 * to a source column. Auto-matches by name on first selection.
 */
export function ColumnConfigModal({ table, column, onClose, onSaved }: Props) {
  const { t } = useT();
  // First-touch guard: flips true on any input change inside the form so
  // an accidental backdrop click can't lose prompt/variable mappings.
  const [touched, setTouched] = useState(false);
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState("");

  const [selectedPromptId, setSelectedPromptId] = useState<number | null>(
    column.prompt_id,
  );
  const [promptDetail, setPromptDetail] = useState<PromptDetail | null>(null);
  const [variableMap, setVariableMap] = useState<Record<string, number | null>>(
    Object.fromEntries(
      Object.entries(column.variable_map ?? {}).map(([k, v]) => [k, Number(v)]),
    ),
  );

  const [previewRowId, setPreviewRowId] = useState<number | null>(
    table.rows[0]?.id ?? null,
  );
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewMissing, setPreviewMissing] = useState<string[]>([]);

  // Per-column provider/model override (null = workspace default).
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [providerCode, setProviderCode] = useState<string | null>(column.provider_code);
  const [model, setModel] = useState<string | null>(column.model);
  // Output-token ceiling for this column; null = inherit the global default.
  const [maxOutputTokens, setMaxOutputTokens] = useState<number | null>(
    column.max_output_tokens ?? null,
  );
  // Grounding source (null = off). Only valid on Vertex + a Gemini model.
  const [grounding, setGrounding] = useState<string | null>(
    column.grounding ?? null,
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // Other columns that can be sources for variables (any column except this one).
  const sourceColumns = useMemo(
    () => table.columns.filter((c) => c.id !== column.id),
    [table.columns, column.id],
  );

  // Initial data
  useEffect(() => {
    Promise.all([listPrompts({ page_size: 500 }), listCategories(), listEnabledProviders()])
      .then(([ps, cs, prv]) => {
        setPrompts(ps.items);
        setCategories(cs);
        setProviders(prv);
      })
      .catch((e) => setError(e));
  }, []);

  // When the user picks a provider, default the model to that provider's default
  // unless they've already selected one.
  useEffect(() => {
    if (providerCode == null) {
      // Workspace-default: clear the explicit model too.
      return;
    }
    const p = providers.find((x) => x.code === providerCode);
    if (model == null && p?.default_model) {
      setModel(p.default_model);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerCode, providers]);

  const selectedProvider = providers.find((p) => p.code === providerCode);

  // Grounding is a Vertex-Gemini capability (only that path wires the Google
  // Search tool). Offer it only when the column runs on Vertex with a non-Claude
  // model, matching the server-side guard.
  const groundingAllowed =
    providerCode === "vertex" &&
    !(model ?? "").trim().toLowerCase().startsWith("claude");

  // When prompt changes, fetch its detail (variables list).
  // Abort superseded fetches via an `ignored` flag so a stale result can't
  // overwrite the active prompt's variable map.
  useEffect(() => {
    if (selectedPromptId == null) {
      setPromptDetail(null);
      return;
    }
    let ignored = false;
    getPrompt(selectedPromptId)
      .then((p) => {
        if (ignored) return;
        setPromptDetail(p);
        // Auto-match: for any variable not already mapped, look for a source
        // column whose name matches case-insensitively.
        setVariableMap((cur) => {
          const next = { ...cur };
          for (const v of p.variables) {
            if (next[v] != null) continue;
            const match = sourceColumns.find(
              (c) => c.name.trim().toLowerCase() === v.toLowerCase(),
            );
            next[v] = match?.id ?? null;
          }
          return next;
        });
      })
      .catch((e) => {
        if (!ignored) setError(e);
      });
    return () => {
      ignored = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPromptId]);

  // When user picks a row to preview, fetch the rendered prompt
  useEffect(() => {
    if (!promptDetail || previewRowId == null) {
      setPreviewText(null);
      return;
    }
    // Build the variables dict from the row's cell values
    const cellLookup = new Map<string, string>();
    for (const c of table.cells) {
      if (c.row_id === previewRowId && c.value != null) {
        cellLookup.set(`${c.column_id}`, c.value);
      }
    }
    const vars: Record<string, string> = {};
    for (const [varName, sourceColId] of Object.entries(variableMap)) {
      if (sourceColId == null) continue;
      vars[varName] = cellLookup.get(`${sourceColId}`) ?? "";
    }
    renderPrompt({ prompt_id: promptDetail.id, variables: vars })
      .then((r) => {
        setPreviewText(r.rendered_prompt);
        setPreviewMissing(r.missing_variables);
      })
      .catch(() => setPreviewText(null));
  }, [promptDetail, previewRowId, variableMap, table.cells]);

  const filteredPrompts = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return prompts;
    return prompts.filter((p) => p.name.toLowerCase().includes(q));
  }, [prompts, search]);

  const promptsByCat = useMemo(() => {
    const groups = new Map<string, PromptListItem[]>();
    const catName = (id: number | null) =>
      id == null ? t("colCfg.noFolder") : categories.find((c) => c.id === id)?.name ?? t("colCfg.noFolder");
    for (const p of filteredPrompts) {
      const k = catName(p.category_id);
      const arr = groups.get(k) ?? [];
      arr.push(p);
      groups.set(k, arr);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [filteredPrompts, categories]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      // Drop nulls from the map; backend expects {var_name: column_id} only.
      const cleanMap: Record<string, number> = {};
      for (const [k, v] of Object.entries(variableMap)) {
        if (v != null) cleanMap[k] = v;
      }
      const updated = await updateColumn(table.id, column.id, {
        kind: "output",
        prompt_id: selectedPromptId ?? null,
        variable_map: cleanMap,
        provider_code: providerCode,
        model: model && model.trim() ? model.trim() : null,
        max_output_tokens:
          maxOutputTokens && maxOutputTokens > 0 ? maxOutputTokens : null,
        grounding: groundingAllowed
          ? (grounding as "google_search" | null)
          : null,
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      console.error("[Bulk] save column config failed", err);
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  async function onClearPrompt() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateColumn(table.id, column.id, {
        prompt_id: null,
        variable_map: {},
      });
      onSaved(updated);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal onClose={onClose} size="max-w-3xl" dirty={touched}>
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
        {t("colCfg.title")} <span className="font-mono">{column.name}</span>
      </h2>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("colCfg.subtitle")}
      </p>

      <form
        onSubmit={onSubmit}
        onChange={() => {
          if (!touched) setTouched(true);
        }}
        className="mt-5 space-y-5"
      >
        {/* Prompt picker */}
        <div>
          <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("colCfg.prompt")}
          </label>
          <input
            type="text"
            placeholder={t("colCfg.searchPrompts")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <div className="mt-2 max-h-44 space-y-2 overflow-y-auto rounded-md border border-neutral-200 p-2 text-sm dark:border-neutral-800">
            {promptsByCat.length === 0 && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                {t("colCfg.noPromptsMatch")}
              </p>
            )}
            {promptsByCat.map(([catName, items]) => (
              <div key={catName}>
                <p className="px-1 text-[10px] uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                  {catName}
                </p>
                <ul>
                  {items.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPromptId(p.id)}
                        className={
                          "block w-full truncate rounded px-2 py-1 text-left " +
                          (selectedPromptId === p.id
                            ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                            : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800")
                        }
                      >
                        {p.name}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* Variable mapping */}
        {promptDetail && (
          <div>
            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {t("colCfg.variables", { count: promptDetail.variables.length })}
            </p>
            {promptDetail.variables.length === 0 ? (
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {t("colCfg.noVariables")}
              </p>
            ) : (
              <ul className="mt-2 space-y-2">
                {promptDetail.variables.map((v) => {
                  const sourceColId = variableMap[v] ?? null;
                  const isAuto =
                    sourceColId != null &&
                    sourceColumns.find(
                      (c) =>
                        c.id === sourceColId &&
                        c.name.trim().toLowerCase() === v.toLowerCase(),
                    );
                  return (
                    <li
                      key={v}
                      className="flex items-center gap-3 rounded-md border border-neutral-200 px-3 py-2 dark:border-neutral-800"
                    >
                      <code className="shrink-0 rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200">
                        {`{{${v}}}`}
                      </code>
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        ←
                      </span>
                      <select
                        value={sourceColId ?? ""}
                        onChange={(e) =>
                          setVariableMap((cur) => ({
                            ...cur,
                            [v]: e.target.value === "" ? null : Number(e.target.value),
                          }))
                        }
                        className="flex-1 rounded-md border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                      >
                        <option value="">{t("colCfg.pickSourceColumn")}</option>
                        {sourceColumns.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} {c.kind === "output" ? t("colCfg.outputSuffix") : ""}
                          </option>
                        ))}
                      </select>
                      {isAuto && (
                        <span className="text-[10px] uppercase text-green-600 dark:text-green-400">
                          {t("colCfg.auto")}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}

        {/* Provider + Model override */}
        <div>
<p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
            {t("colCfg.providerModel")}{" "}
            <span className="text-xs font-normal text-neutral-500 dark:text-neutral-400">
              {t("colCfg.optionalOverride")}
            </span>
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("newPrompt.providerLabel")}
              <select
                value={providerCode ?? ""}
                onChange={(e) => {
                  const v = e.target.value || null;
                  setProviderCode(v);
                  setModel(null);
                  // Grounding only survives on Vertex — reset it otherwise so
                  // the config can't be saved into a guaranteed 400.
                  if (v !== "vertex") setGrounding(null);
                }}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
              >
                <option value="">{t("colCfg.useWorkspaceDefault")}</option>
                {providers.map((p) => (
                  <option key={p.code} value={p.code} disabled={!p.has_api_key}>
                    {p.display_name}
                    {!p.has_api_key && ` ${t("newPrompt.providerNoApiKey")}`}
                  </option>
                ))}
              </select>
              {selectedProvider && !selectedProvider.has_api_key && (
                <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-400">
                  {t("colCfg.providerNoKeyHint")}
                </p>
              )}
            </label>
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("newPrompt.modelLabel")}
              <select
                value={model ?? ""}
                onChange={(e) => setModel(e.target.value || null)}
                disabled={providerCode == null}
                className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
              >
                <option value="">
                  {providerCode == null
                    ? t("colCfg.usesProviderDefault")
                    : t("colCfg.useProviderDefault")}
                </option>
                {selectedProvider?.available_models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("colCfg.inheritHint")}
          </p>
          {/* Long-form columns (full articles) need a bigger ceiling than short
              ones (titles, metas). Blank inherits the global default. */}
          <label className="mt-3 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("colCfg.maxOutputTokens")}
            <input
              type="number"
              min={1}
              max={200000}
              step={256}
              value={maxOutputTokens ?? ""}
              placeholder={t("colCfg.maxOutputTokensPlaceholder")}
              onChange={(e) =>
                setMaxOutputTokens(
                  e.target.value.trim() === "" ? null : Number(e.target.value),
                )
              }
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-neutral-500 focus:outline-none focus:ring-1 focus:ring-neutral-500 dark:border-neutral-700 dark:bg-neutral-900"
            />
            <span className="mt-1 block font-normal text-neutral-500 dark:text-neutral-400">
              {t("colCfg.maxOutputTokensHint")}
            </span>
          </label>

          {/* Grounding: research the topic against live sources. Vertex+Gemini
              only — disabled (and forced Off) on any other provider/model. */}
          <label className="mt-3 block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("colCfg.grounding")}
            <select
              value={grounding ?? ""}
              onChange={(e) => setGrounding(e.target.value || null)}
              disabled={!groundingAllowed}
              className="mt-1 block w-full rounded-md border border-neutral-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-900"
            >
              <option value="">{t("colCfg.groundingOff")}</option>
              <option value="google_search">
                {t("colCfg.groundingGoogleSearch")}
              </option>
            </select>
            <span className="mt-1 block font-normal text-neutral-500 dark:text-neutral-400">
              {groundingAllowed
                ? t("colCfg.groundingHint")
                : t("colCfg.groundingRequiresVertex")}
            </span>
          </label>
        </div>

        {/* Preview */}
        {promptDetail && table.rows.length > 0 && (
          <div>
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                {t("colCfg.preview")}
              </p>
              <select
                value={previewRowId ?? ""}
                onChange={(e) => setPreviewRowId(Number(e.target.value))}
                className="rounded-md border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
              >
                {table.rows.map((r, i) => (
                  <option key={r.id} value={r.id}>
                    {t("colCfg.rowHash", { n: i + 1 })}
                  </option>
                ))}
              </select>
            </div>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-neutral-50 p-3 font-mono text-xs text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
              {previewText ?? t("colCfg.previewLoading")}
            </pre>
            {previewMissing.length > 0 && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                {t("colCfg.unfilledVarsForRow", { vars: previewMissing.map((m) => `{{${m}}}`).join(", ") })}
              </p>
            )}
          </div>
        )}

        {error != null && <ErrorPanel title={t("colCfg.saveFailed")} error={error} />}

        <div className="flex items-center justify-between border-t border-neutral-200 pt-4 dark:border-neutral-800">
          <button
            type="button"
            onClick={onClearPrompt}
            disabled={saving || column.prompt_id == null}
            className="text-xs font-medium text-red-600 hover:underline disabled:opacity-40 dark:text-red-400"
          >
            {t("colCfg.clearAssignment")}
          </button>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={saving || selectedPromptId == null}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
