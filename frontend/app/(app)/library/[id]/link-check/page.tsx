"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { LinkCheckStatusChip } from "@/components/LinkCheckStatusChip";
import { RunRowActions } from "@/components/RunRowActions";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getTable } from "@/lib/library";
import {
  deleteLinkCheckRun,
  listLinkCheckRuns,
  renameLinkCheckRun,
  startLinkCheck,
  type LinkCheckRun,
  type LinkTreatment,
} from "@/lib/linkCheck";
import type { BulkColumn, BulkTable } from "@/lib/types";

export default function LinkCheckPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tableId = Number(id);
  const { t } = useT();

  const [table, setTable] = useState<BulkTable | null>(null);
  const [columnIds, setColumnIds] = useState<Set<number>>(new Set());
  // Neither check is pre-selected — the user picks the method(s) to run.
  const [checkJuxtapose, setCheckJuxtapose] = useState(false);
  const [checkCrawl, setCheckCrawl] = useState(false);
  const [includeOk, setIncludeOk] = useState(false);
  const [expectedColumnIds, setExpectedColumnIds] = useState<Set<number>>(
    new Set(),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<LinkCheckRun[]>([]);

  // 3rd mode — translation links. Exclusive of crawl/juxtapose.
  const [checkTranslation, setCheckTranslation] = useState(false);
  const [tOriginal, setTOriginal] = useState<number | null>(null);
  const [tTranslated, setTTranslated] = useState<number | null>(null);
  const [tLang, setTLang] = useState<number | null>(null);
  const [tDomainCols, setTDomainCols] = useState<Set<number>>(new Set());
  const [tProductDomain, setTProductDomain] = useState("");
  const [tExceptions, setTExceptions] = useState("");
  const [tInternal, setTInternal] = useState<LinkTreatment>("skip");
  const [tExternal, setTExternal] = useState<LinkTreatment>("skip");

  useEffect(() => {
    if (!Number.isFinite(tableId)) return;
    // This page only needs the table name + columns (both returned in full
    // regardless of paging). Request a 1-row page so a large table's cells
    // don't bloat the payload and block the history list from rendering.
    getTable(tableId, { page: 1, page_size: 1 })
      .then(setTable)
      .catch((e) => setError(String(e)));
  }, [tableId]);

  const loadRuns = useCallback(() => {
    listLinkCheckRuns(tableId).then(setRuns).catch(() => {});
  }, [tableId]);
  useEffect(() => loadRuns(), [loadRuns]);

  const columns = table?.columns ?? [];
  const tRoleIds = [tOriginal, tTranslated, tLang].filter(
    (x): x is number => x != null,
  );
  const canRunTranslation =
    tOriginal != null &&
    tTranslated != null &&
    tLang != null &&
    new Set(tRoleIds).size === 3;
  const canRun = checkTranslation
    ? canRunTranslation
    : columnIds.size > 0 &&
      (checkJuxtapose || checkCrawl) &&
      (!checkJuxtapose || expectedColumnIds.size > 0);

  function toggleSet(
    setter: React.Dispatch<React.SetStateAction<Set<number>>>,
    cid: number,
  ) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  }

  async function run() {
    if (!canRun) return;
    setBusy(true);
    setError(null);
    try {
      const r = await startLinkCheck(
        tableId,
        checkTranslation
          ? {
              translation: {
                original_column_id: tOriginal!,
                translated_column_id: tTranslated!,
                lang_column_id: tLang!,
                internal_domain_column_ids: Array.from(tDomainCols),
                product_domain: tProductDomain,
                exceptions: tExceptions,
                internal_treatment: tInternal,
                external_treatment: tExternal,
              },
            }
          : {
              column_ids: Array.from(columnIds),
              expected_column_ids: checkJuxtapose
                ? Array.from(expectedColumnIds)
                : [],
              check_juxtapose: checkJuxtapose,
              check_crawl: checkCrawl,
              include_ok: checkCrawl ? includeOk : false,
            },
      );
      window.location.href = `/library/${tableId}/link-check/runs/${r.id}`;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-6">
      <div className="mb-4">
        <Link
          href={`/library/${tableId}`}
          className="text-sm text-neutral-600 hover:underline dark:text-neutral-400"
        >
          {t("linkCheck.backToTable")}
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("linkCheck.title")}
      </h1>
      {table && (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          {t("linkCheck.onTable", { name: table.name })}
        </p>
      )}

      <section className="mt-5 rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900">
        {/* columns to scan — only for the crawl / juxtapose methods */}
        {!checkTranslation && (
          <div>
            <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
              {t("linkCheck.columnsLabel")}
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {columns.map((c) => {
                const on = columnIds.has(c.id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => toggleSet(setColumnIds, c.id)}
                    className={
                      "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                      (on
                        ? "bg-blue-600 text-white ring-blue-600"
                        : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                    }
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* methods */}
        <div className="mt-4 grid gap-2">
          <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
            {t("linkCheck.checksLabel")}
          </span>
          {!checkTranslation && (
            <>
              <Toggle
                checked={checkCrawl}
                onChange={setCheckCrawl}
                label={t("linkCheck.optCrawl")}
                hint={t("linkCheck.optCrawlHint")}
              />
              {checkCrawl && (
                <div className="ml-6">
                  <Toggle
                    checked={includeOk}
                    onChange={setIncludeOk}
                    label={t("linkCheck.optIncludeOk")}
                    hint={t("linkCheck.optIncludeOkHint")}
                  />
                </div>
              )}
              <Toggle
                checked={checkJuxtapose}
                onChange={setCheckJuxtapose}
                label={t("linkCheck.optJuxtapose")}
                hint={t("linkCheck.optJuxtaposeHint")}
              />
              {checkJuxtapose && (
                <div className="ml-6 mt-1">
                  <span className="text-xs text-neutral-600 dark:text-neutral-400">
                    {t("linkCheck.expectedLabel")}
                  </span>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {columns.map((c) => {
                      const on = expectedColumnIds.has(c.id);
                      return (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => toggleSet(setExpectedColumnIds, c.id)}
                          className={
                            "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                            (on
                              ? "bg-violet-600 text-white ring-violet-600"
                              : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
                          }
                        >
                          {c.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}
          {/* 3rd method — translation links, listed last (exclusive) */}
          <Toggle
            checked={checkTranslation}
            onChange={setCheckTranslation}
            label={t("linkCheck.optTranslation")}
            hint={t("linkCheck.optTranslationHint")}
          />
        </div>

        {checkTranslation && (
          <div className="mt-4 grid gap-4 border-t border-neutral-100 pt-4 dark:border-neutral-800">
            <RolePicker
              label={t("linkCheck.tOriginal")}
              hint={t("linkCheck.tOriginalHint")}
              columns={columns}
              value={tOriginal}
              onChange={setTOriginal}
              accent="blue"
            />
            <RolePicker
              label={t("linkCheck.tTranslated")}
              hint={t("linkCheck.tTranslatedHint")}
              columns={columns}
              value={tTranslated}
              onChange={setTTranslated}
              accent="green"
            />
            <RolePicker
              label={t("linkCheck.tLang")}
              hint={t("linkCheck.tLangHint")}
              columns={columns}
              value={tLang}
              onChange={setTLang}
              accent="amber"
            />

            <MultiColumnPicker
              label={t("linkCheck.tDomainCols")}
              hint={t("linkCheck.tDomainColsHint")}
              columns={columns}
              value={tDomainCols}
              onToggle={(id) => toggleSet(setTDomainCols, id)}
            />

            <label className="block">
              <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                {t("linkCheck.tProductDomain")}
              </span>
              <span className="block text-xs text-neutral-400 dark:text-neutral-500">
                {t("linkCheck.tProductDomainHint")}
              </span>
              <input
                type="text"
                value={tProductDomain}
                onChange={(e) => setTProductDomain(e.target.value)}
                placeholder="shop.example.com"
                className="mt-1 block w-full rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <TreatmentSelect
                label={t("linkCheck.tInternalTreatment")}
                value={tInternal}
                onChange={setTInternal}
                t={t}
              />
              <TreatmentSelect
                label={t("linkCheck.tExternalTreatment")}
                value={tExternal}
                onChange={setTExternal}
                t={t}
              />
            </div>

            <TextAreaField
              label={t("linkCheck.tExceptions")}
              hint={t("linkCheck.tExceptionsHint")}
              value={tExceptions}
              onChange={setTExceptions}
              placeholder={
                "es, /product/widget, /products/gadget\nde, https://example.com/x"
              }
            />
          </div>
        )}

        <div className="mt-4">
          <button
            type="button"
            disabled={!canRun || busy}
            onClick={run}
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
          >
            {t("linkCheck.checkBtn")}
          </button>
        </div>
      </section>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {runs.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
            {t("linkCheck.historyHeading")}
          </h2>
          <ul className="mt-2 divide-y divide-neutral-100 rounded-lg border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {runs.map((r) => {
              const mode = r.translation_config
                ? t("linkCheckRun.translationMode")
                : [
                    r.check_crawl && t("linkCheckRun.modeCrawl"),
                    r.check_juxtapose && t("linkCheckRun.modeJuxtapose"),
                  ]
                    .filter(Boolean)
                    .join(" + ");
              const label = r.name
                ? r.name
                : mode
                  ? t("linkCheck.runLabelWithMode", { id: r.id, mode })
                  : t("linkCheck.runLabel", { id: r.id });
              return (
              <li key={r.id}>
                <Link
                  href={`/library/${tableId}/link-check/runs/${r.id}`}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900"
                >
                  <span className="min-w-0 truncate text-neutral-700 dark:text-neutral-300">
                    {label}
                    <span className="ml-2 text-xs text-neutral-400">
                      {new Date(r.created_at).toLocaleString()}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-2 text-xs">
                    <LinkCheckStatusChip status={r.status} />
                    {(r.broken_count + r.omitted_count + r.hallucinated_count) >
                      0 && (
                      <span className="text-red-600 dark:text-red-400">
                        {t("linkCheck.violCount", {
                          n:
                            r.broken_count +
                            r.omitted_count +
                            r.hallucinated_count,
                        })}
                      </span>
                    )}
                    <RunRowActions
                      name={r.name}
                      canDelete={r.status !== "queued" && r.status !== "running"}
                      onRename={async (n) => {
                        await renameLinkCheckRun(r.id, n);
                        loadRuns();
                      }}
                      onDelete={async () => {
                        await deleteLinkCheckRun(r.id);
                        loadRuns();
                      }}
                    />
                  </span>
                </Link>
              </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}

/** Single-select column picker for a translation role (Original/Translated/Lang). */
function RolePicker({
  label,
  hint,
  columns,
  value,
  onChange,
  accent,
}: {
  label: string;
  hint?: string;
  columns: BulkColumn[];
  value: number | null;
  onChange: (v: number | null) => void;
  accent: "blue" | "green" | "amber";
}) {
  const onCls =
    accent === "blue"
      ? "bg-blue-600 text-white ring-blue-600"
      : accent === "green"
        ? "bg-green-600 text-white ring-green-600"
        : "bg-amber-500 text-white ring-amber-500";
  return (
    <div>
      <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
        {label}
      </span>
      {hint && (
        <span className="block text-xs text-neutral-400 dark:text-neutral-500">
          {hint}
        </span>
      )}
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {columns.map((c) => {
          const on = value === c.id;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onChange(on ? null : c.id)}
              className={
                "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                (on
                  ? onCls
                  : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
              }
            >
              {c.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Multi-select column picker (e.g. the internal-domain columns). */
function MultiColumnPicker({
  label,
  hint,
  columns,
  value,
  onToggle,
}: {
  label: string;
  hint?: string;
  columns: BulkColumn[];
  value: Set<number>;
  onToggle: (id: number) => void;
}) {
  return (
    <div>
      <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
        {label}
      </span>
      {hint && (
        <span className="block text-xs text-neutral-400 dark:text-neutral-500">
          {hint}
        </span>
      )}
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {columns.map((c) => {
          const on = value.has(c.id);
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onToggle(c.id)}
              className={
                "rounded-full px-2.5 py-1 text-xs ring-1 ring-inset " +
                (on
                  ? "bg-teal-600 text-white ring-teal-600"
                  : "text-neutral-600 ring-neutral-300 hover:bg-neutral-50 dark:text-neutral-400 dark:ring-neutral-700 dark:hover:bg-neutral-800")
              }
            >
              {c.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TreatmentSelect({
  label,
  value,
  onChange,
  t,
}: {
  label: string;
  value: LinkTreatment;
  onChange: (v: LinkTreatment) => void;
  t: ReturnType<typeof useT>["t"];
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as LinkTreatment)}
        className="mt-1 block w-full rounded-md border border-neutral-300 px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
      >
        <option value="skip">{t("linkCheck.treatSkip")}</option>
        <option value="localize">{t("linkCheck.treatLocalize")}</option>
      </select>
    </label>
  );
}

function TextAreaField({
  label,
  hint,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
        {label}
      </span>
      {hint && (
        <span className="block text-xs text-neutral-400 dark:text-neutral-500">
          {hint}
        </span>
      )}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={3}
        className="mt-1 block w-full rounded-md border border-neutral-300 px-2 py-1.5 font-mono text-xs dark:border-neutral-700 dark:bg-neutral-900"
      />
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-sm text-neutral-700 dark:text-neutral-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-3.5 w-3.5 rounded border-neutral-300 dark:border-neutral-600"
      />
      <span>
        {label}
        {hint && (
          <span className="block text-xs text-neutral-400 dark:text-neutral-500">
            {hint}
          </span>
        )}
      </span>
    </label>
  );
}
