"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useMemo, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { ApiError } from "@/lib/api";
import {
  createAiHelperRun,
  extractVariables,
  listAiHelperRuns,
  previewAiHelperRun,
  uniqueKey,
  type AiHelperEngine,
  type AiHelperOutputMode,
  type AiHelperPreview,
  type AiHelperRunCreate,
  type AiHelperRunListItem,
} from "@/lib/aiHelper";
import { listEnabledProviders } from "@/lib/generate";
import { useT } from "@/lib/i18n-context";
import { getTable } from "@/lib/library";
import { listPrompts } from "@/lib/prompts";
import type { BulkTable, EnabledProvider, PromptListItem } from "@/lib/types";

type OutputRow = {
  column_id: number | "";
  mode: AiHelperOutputMode;
  key: string;
  prompt: string;
};

const NEW_OUTPUT: OutputRow = { column_id: "", mode: "write", key: "", prompt: "" };

export default function AiHelperPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tableId = Number(id);
  const { t } = useT();
  const router = useRouter();

  const [table, setTable] = useState<BulkTable | null>(null);
  const [providers, setProviders] = useState<EnabledProvider[]>([]);
  const [prompts, setPrompts] = useState<PromptListItem[]>([]);
  const [runs, setRuns] = useState<AiHelperRunListItem[]>([]);

  const [engine, setEngine] = useState<AiHelperEngine>("structured");
  const [prompt, setPrompt] = useState("");
  const [promptId, setPromptId] = useState<number | null>(null);
  const [varMap, setVarMap] = useState<Record<string, number | "">>({});
  const [outputs, setOutputs] = useState<OutputRow[]>([{ ...NEW_OUTPUT }]);
  const [inputScope, setInputScope] = useState<"full" | "first_pct">("full");
  const [inputPct, setInputPct] = useState(10);
  const [sliceColumnId, setSliceColumnId] = useState<number | "">("");
  const [providerCode, setProviderCode] = useState("");
  const [model, setModel] = useState("");
  const [maxOut, setMaxOut] = useState("");
  const [rowsMode, setRowsMode] = useState<"all" | "first" | "range">("all");
  const [rowsN, setRowsN] = useState(20);
  const [rowsFrom, setRowsFrom] = useState(1);
  const [rowsTo, setRowsTo] = useState(1);

  const [preview, setPreview] = useState<AiHelperPreview | null>(null);
  const [busy, setBusy] = useState<"" | "preview" | "run">("");
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    getTable(tableId, { page: 1, page_size: 1 }).then(setTable).catch((e) =>
      setError(String(e)),
    );
    listEnabledProviders().then(setProviders).catch(() => {});
    listPrompts({ page_size: 100 }).then((r) => setPrompts(r.items)).catch(() => {});
    listAiHelperRuns(tableId).then(setRuns).catch(() => {});
  }, [tableId]);

  const columns = table?.columns ?? [];

  // Variables come from the base prompt (structured) or the union of every
  // output's prompt (per_output).
  const vars = useMemo(() => {
    if (engine === "structured") return extractVariables(prompt);
    const seen: string[] = [];
    for (const o of outputs)
      for (const v of extractVariables(o.prompt))
        if (!seen.includes(v)) seen.push(v);
    return seen;
  }, [engine, prompt, outputs]);

  const mappedCols = useMemo(
    () => new Set(Object.values(varMap).filter((v): v is number => v !== "")),
    [varMap],
  );

  function reset() {
    setPreview(null);
    setConfirming(false);
  }

  // ----- outputs list -----
  function patchOutput(idx: number, patch: Partial<OutputRow>) {
    reset();
    setOutputs((prev) => prev.map((o, i) => (i === idx ? { ...o, ...patch } : o)));
  }
  function addOutput() {
    reset();
    setOutputs((prev) => [...prev, { ...NEW_OUTPUT }]);
  }
  function removeOutput(idx: number) {
    reset();
    setOutputs((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== idx) : prev));
  }
  function setOutputColumn(idx: number, val: number | "") {
    const colName = columns.find((c) => c.id === val)?.name ?? "";
    const taken = new Set(
      outputs.filter((_, i) => i !== idx).map((o) => o.key).filter(Boolean),
    );
    patchOutput(idx, {
      column_id: val,
      key: val === "" ? "" : uniqueKey(colName, taken),
    });
  }

  // ----- validation -----
  const filledCols = outputs.map((o) => o.column_id).filter((c) => c !== "");
  const outputsFilled = outputs.length > 0 && filledCols.length === outputs.length;
  const outputColsDistinct = new Set(filledCols).size === filledCols.length;
  const keysOk =
    engine !== "structured" ||
    (outputs.every((o) => o.key.trim() !== "") &&
      new Set(outputs.map((o) => o.key.trim())).size === outputs.length);
  const perOutputPromptsOk =
    engine !== "per_output" || outputs.every((o) => o.prompt.trim() !== "");
  const editOutputsOk = outputs.every(
    (o) =>
      o.mode !== "edit" ||
      (o.column_id !== "" && mappedCols.has(Number(o.column_id))),
  );
  const basePromptOk = engine !== "structured" || prompt.trim() !== "";
  const allVarsMapped = vars.every((v) => varMap[v] !== "" && varMap[v] != null);
  const sliceOk =
    inputScope === "full" ||
    (inputPct >= 1 && inputPct <= 100 && sliceColumnId !== "");
  const rowsOk =
    rowsMode === "all" ||
    (rowsMode === "first" && rowsN >= 1) ||
    (rowsMode === "range" && rowsFrom >= 1 && rowsTo >= rowsFrom);
  const canRun =
    basePromptOk &&
    outputsFilled &&
    outputColsDistinct &&
    keysOk &&
    perOutputPromptsOk &&
    editOutputsOk &&
    allVarsMapped &&
    sliceOk &&
    rowsOk &&
    busy === "";

  const provider = providers.find((p) => p.code === providerCode);

  async function resolveRowIds(): Promise<number[]> {
    if (rowsMode === "all") return [];
    if (rowsMode === "first") {
      const t2 = await getTable(tableId, { page: 1, page_size: Math.max(1, rowsN) });
      return (t2.rows ?? []).map((r) => r.id);
    }
    // range: 1-indexed row numbers (inclusive); from==to selects one row.
    const from = Math.max(1, rowsFrom);
    const to = Math.max(from, rowsTo);
    const t2 = await getTable(tableId, { page: 1, page_size: to });
    return (t2.rows ?? []).slice(from - 1, to).map((r) => r.id);
  }

  function buildPayload(rowIds: number[]): AiHelperRunCreate {
    const variable_map: Record<string, number> = {};
    for (const v of vars) {
      const cid = varMap[v];
      if (cid !== "" && cid != null) variable_map[v] = cid;
    }
    return {
      engine,
      prompt: engine === "structured" ? prompt.trim() : "",
      prompt_id: engine === "structured" ? promptId : null,
      variable_map,
      outputs: outputs
        .filter((o) => o.column_id !== "")
        .map((o) => ({
          column_id: Number(o.column_id),
          mode: o.mode,
          key: o.key.trim(),
          prompt: o.prompt,
        })),
      provider_code: providerCode || null,
      model: model || null,
      max_output_tokens: maxOut ? Number(maxOut) : null,
      input_scope: inputScope,
      input_pct: inputScope === "first_pct" ? inputPct : null,
      slice_column_id:
        inputScope === "first_pct" && sliceColumnId !== ""
          ? Number(sliceColumnId)
          : null,
      row_ids: rowIds,
    };
  }

  async function doPreview() {
    if (!canRun) return;
    setBusy("preview");
    setError(null);
    try {
      const rowIds = await resolveRowIds();
      setPreview(await previewAiHelperRun(tableId, buildPayload(rowIds)));
      setConfirming(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function doRun() {
    setBusy("run");
    setError(null);
    try {
      const rowIds = await resolveRowIds();
      const run = await createAiHelperRun(tableId, buildPayload(rowIds));
      router.push(`/library/${tableId}/ai-helper/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy("");
    }
  }

  const colSelect = (
    value: number | "",
    onChange: (v: number | "") => void,
    withNone = true,
  ) => (
    <select
      value={value}
      onChange={(e) => {
        reset();
        onChange(e.target.value ? Number(e.target.value) : "");
      }}
      className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
    >
      {withNone && <option value="">{t("aiHelper.pickColumn")}</option>}
      {columns.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </select>
  );

  return (
    <main className="mx-auto max-w-3xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("aiHelper.backToTable")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("aiHelper.title")}
      </h1>
      {table && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("aiHelper.onTable", { name: table.name })}
        </p>
      )}

      <section className="mt-5 space-y-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        {/* Engine */}
        <div>
          <span className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("aiHelper.engineLabel")}
          </span>
          <div className="mt-1 flex flex-col gap-1.5 text-sm">
            {(["structured", "per_output"] as const).map((e) => (
              <label key={e} className="flex cursor-pointer items-start gap-2">
                <input
                  type="radio"
                  className="mt-0.5"
                  checked={engine === e}
                  onChange={() => {
                    reset();
                    setEngine(e);
                  }}
                />
                <span>
                  <span className="font-medium">
                    {t(`aiHelper.engine.${e}` as never)}
                  </span>
                  <span className="ml-1.5 text-xs text-neutral-500 dark:text-neutral-400">
                    {t(`aiHelper.engineHint.${e}` as never)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Base prompt (structured only) */}
        {engine === "structured" && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("aiHelper.promptLabel")}
              </span>
              {prompts.length > 0 && (
                <select
                  value={promptId ?? ""}
                  onChange={(e) => {
                    reset();
                    const pid = e.target.value ? Number(e.target.value) : null;
                    setPromptId(pid);
                    const p = prompts.find((x) => x.id === pid);
                    if (p?.current_version?.content)
                      setPrompt(p.current_version.content);
                  }}
                  className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{t("aiHelper.fromLibrary")}</option>
                  {prompts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <textarea
              value={prompt}
              onChange={(e) => {
                reset();
                setPrompt(e.target.value);
                setPromptId(null);
              }}
              rows={4}
              placeholder={t("aiHelper.promptPlaceholderStructured")}
              className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {t("aiHelper.promptHintStructured")}
            </p>
          </div>
        )}

        {/* Variable mapping */}
        {vars.length > 0 && (
          <div>
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("aiHelper.mapLabel")}
            </span>
            <div className="mt-1.5 space-y-1.5">
              {vars.map((v) => (
                <div key={v} className="flex items-center gap-2 text-sm">
                  <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs dark:bg-neutral-800">
                    {`{{${v}}}`}
                  </code>
                  <span className="text-neutral-400">→</span>
                  {colSelect(varMap[v] ?? "", (val) =>
                    setVarMap((m) => ({ ...m, [v]: val })),
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Outputs */}
        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("aiHelper.outputsLabel")}
            </span>
            <button
              type="button"
              onClick={addOutput}
              className="rounded-md border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("aiHelper.addOutput")}
            </button>
          </div>
          <div className="mt-2 space-y-2.5">
            {outputs.map((o, idx) => {
              const editWarn =
                o.mode === "edit" &&
                o.column_id !== "" &&
                !mappedCols.has(Number(o.column_id));
              return (
                <div
                  key={idx}
                  className="rounded-md border border-neutral-200 p-2.5 dark:border-neutral-800"
                >
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    {colSelect(o.column_id, (val) => setOutputColumn(idx, val))}
                    <select
                      value={o.mode}
                      onChange={(e) =>
                        patchOutput(idx, {
                          mode: e.target.value as AiHelperOutputMode,
                        })
                      }
                      className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    >
                      <option value="write">{t("aiHelper.out.write")}</option>
                      <option value="edit">{t("aiHelper.out.edit")}</option>
                    </select>
                    {engine === "structured" && (
                      <span className="flex items-center gap-1">
                        <span className="text-xs text-neutral-500">
                          {t("aiHelper.out.key")}
                        </span>
                        <input
                          type="text"
                          value={o.key}
                          onChange={(e) =>
                            patchOutput(idx, { key: e.target.value })
                          }
                          placeholder="key"
                          className="w-28 rounded-md border border-neutral-300 bg-white px-2 py-1 font-mono text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                        />
                      </span>
                    )}
                    {outputs.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeOutput(idx)}
                        className="ml-auto rounded-md px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-red-600 dark:hover:bg-neutral-800"
                        aria-label={t("aiHelper.removeOutput")}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {editWarn && (
                    <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">
                      {t("aiHelper.editTargetWarn")}
                    </p>
                  )}
                  {engine === "per_output" && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-neutral-500 dark:text-neutral-400">
                          {t("aiHelper.out.prompt")}
                        </span>
                        {prompts.length > 0 && (
                          <select
                            value=""
                            onChange={(e) => {
                              const pid = e.target.value
                                ? Number(e.target.value)
                                : null;
                              const p = prompts.find((x) => x.id === pid);
                              if (p?.current_version?.content)
                                patchOutput(idx, {
                                  prompt: p.current_version.content,
                                });
                            }}
                            className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                          >
                            <option value="">{t("aiHelper.fromLibrary")}</option>
                            {prompts.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                      <textarea
                        value={o.prompt}
                        onChange={(e) =>
                          patchOutput(idx, { prompt: e.target.value })
                        }
                        rows={3}
                        placeholder={t("aiHelper.promptPlaceholder")}
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {!outputColsDistinct && (
            <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">
              {t("aiHelper.outputsDistinctWarn")}
            </p>
          )}
          {engine === "structured" && (
            <p className="mt-1.5 text-xs text-neutral-400 dark:text-neutral-500">
              {t("aiHelper.outputsHintStructured")}
            </p>
          )}
        </div>

        {/* Input scope */}
        <div>
          <span className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("aiHelper.inputScopeLabel")}
          </span>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                checked={inputScope === "full"}
                onChange={() => {
                  reset();
                  setInputScope("full");
                }}
              />
              {t("aiHelper.scopeFull")}
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                checked={inputScope === "first_pct"}
                onChange={() => {
                  reset();
                  setInputScope("first_pct");
                }}
              />
              {t("aiHelper.scopeFirstPct")}
            </label>
            {inputScope === "first_pct" && (
              <span className="flex items-center gap-2">
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={inputPct}
                  onChange={(e) => {
                    reset();
                    setInputPct(Math.max(1, Math.min(100, Number(e.target.value) || 1)));
                  }}
                  className="w-16 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
                <span className="text-xs text-neutral-500">%</span>
                <span className="text-xs text-neutral-500">{t("aiHelper.ofColumn")}</span>
                {colSelect(sliceColumnId, setSliceColumnId)}
              </span>
            )}
          </div>
          {inputScope === "first_pct" && (
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {t("aiHelper.scopeHint")}
            </p>
          )}
        </div>

        {/* Model (optional) + max output */}
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <span className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("aiHelper.modelLabel")}
            </span>
            <div className="mt-1 flex gap-2">
              <select
                value={providerCode}
                onChange={(e) => {
                  reset();
                  setProviderCode(e.target.value);
                  setModel("");
                }}
                className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                <option value="">{t("aiHelper.modelDefault")}</option>
                {providers.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.display_name}
                  </option>
                ))}
              </select>
              {provider && (
                <select
                  value={model}
                  onChange={(e) => {
                    reset();
                    setModel(e.target.value);
                  }}
                  className="rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                >
                  <option value="">{provider.default_model ?? t("aiHelper.modelDefault")}</option>
                  {provider.available_models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>
          <div>
            <span className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("aiHelper.maxOutLabel")}
            </span>
            <input
              type="number"
              min={1}
              value={maxOut}
              onChange={(e) => {
                reset();
                setMaxOut(e.target.value);
              }}
              placeholder={t("aiHelper.maxOutPlaceholder")}
              className="mt-1 w-28 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          </div>
        </div>

        {/* Rows */}
        <div>
          <span className="block text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("aiHelper.rowsLabel")}
          </span>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                checked={rowsMode === "all"}
                onChange={() => {
                  reset();
                  setRowsMode("all");
                }}
              />
              {t("aiHelper.rowsAll")}
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                checked={rowsMode === "first"}
                onChange={() => {
                  reset();
                  setRowsMode("first");
                }}
              />
              {t("aiHelper.rowsTest")}
            </label>
            {rowsMode === "first" && (
              <input
                type="number"
                min={1}
                value={rowsN}
                onChange={(e) => {
                  reset();
                  setRowsN(Math.max(1, Number(e.target.value) || 1));
                }}
                className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            )}
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="radio"
                checked={rowsMode === "range"}
                onChange={() => {
                  reset();
                  setRowsMode("range");
                }}
              />
              {t("aiHelper.rowsRange")}
            </label>
            {rowsMode === "range" && (
              <span className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={1}
                  value={rowsFrom}
                  onChange={(e) => {
                    reset();
                    setRowsFrom(Math.max(1, Number(e.target.value) || 1));
                  }}
                  className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
                <span className="text-xs text-neutral-500">{t("aiHelper.rowsTo")}</span>
                <input
                  type="number"
                  min={rowsFrom}
                  value={rowsTo}
                  onChange={(e) => {
                    reset();
                    setRowsTo(Math.max(1, Number(e.target.value) || 1));
                  }}
                  className="w-20 rounded-md border border-neutral-300 bg-white px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                />
              </span>
            )}
          </div>
          {rowsMode === "range" && (
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              {t("aiHelper.rowsRangeHint", {
                total: table?.total_row_count ?? 0,
              })}
            </p>
          )}
        </div>
      </section>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {/* Preview + run gate */}
      <div className="mt-4">
        {!confirming ? (
          <button
            type="button"
            disabled={!canRun}
            onClick={() => void doPreview()}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {busy === "preview" ? t("common.loading") : t("aiHelper.previewBtn")}
          </button>
        ) : (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-3 dark:border-amber-700/60 dark:bg-amber-950/40">
            <p className="text-sm text-amber-900 dark:text-amber-200">
              {t("aiHelper.confirmLine", {
                rows: preview?.matched_rows ?? 0,
                calls: preview?.est_calls ?? 0,
                cost:
                  preview?.est_cost_usd != null
                    ? `~$${preview.est_cost_usd.toFixed(4)}`
                    : t("aiHelper.costUnknown"),
                model: preview?.model ?? "—",
              })}
            </p>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                disabled={busy !== "" || (preview?.matched_rows ?? 0) === 0}
                onClick={() => void doRun()}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {busy === "run" ? t("aiHelper.starting") : t("aiHelper.runBtn")}
              </button>
              <button
                type="button"
                disabled={busy !== ""}
                onClick={() => setConfirming(false)}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-60 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Run history */}
      {runs.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("aiHelper.historyHeading")}
          </h2>
          <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {runs.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/library/${tableId}/ai-helper/runs/${r.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-300">
                    {r.name || t("aiHelper.runLabel", { id: r.id })}
                    <span className="ml-2 text-xs text-neutral-400">
                      {t(`aiHelper.engineShort.${r.engine}` as never)}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    {r.reverted_at && (
                      <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
                        {t("aiHelper.reverted")}
                      </span>
                    )}
                    <span className="text-neutral-500 dark:text-neutral-400">
                      {t("aiHelper.statDone", { done: r.done, total: r.total })}
                    </span>
                    <LinkCheckStatusChip status={r.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
