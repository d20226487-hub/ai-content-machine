"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getPricing,
  putPricing,
  type PricingTableRow,
} from "@/lib/spend";

/**
 * Admin-only Pricing config.
 *
 * Each row maps a provider:model pair to USD-per-million-tokens for input
 * and output. Cost is computed at usage-event write time, so historical
 * rows preserve whatever rate was active when they happened — editing
 * here only affects new generations.
 *
 * Save is idempotent overwrite: removing a row from the table here clears
 * pricing for that pair entirely.
 */
export function PricingCard() {
  const { t } = useT();
  const [rows, setRows] = useState<PricingTableRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    let ignored = false;
    getPricing()
      .then((r) => {
        if (!ignored) setRows(r);
      })
      .catch((e) => {
        if (!ignored)
          setError(e instanceof ApiError ? e.message : t("common.failedToLoad"));
      });
    return () => {
      ignored = true;
    };
  }, [t]);

  function setRow(idx: number, patch: Partial<PricingTableRow>) {
    setRows((cur) =>
      cur ? cur.map((r, i) => (i === idx ? { ...r, ...patch } : r)) : cur,
    );
  }

  function addRow() {
    setRows((cur) => [
      ...(cur ?? []),
      { provider_code: "", model: "", input_per_1m: null, output_per_1m: null },
    ]);
  }

  function removeRow(idx: number) {
    setRows((cur) => (cur ? cur.filter((_, i) => i !== idx) : cur));
  }

  async function save() {
    if (!rows) return;
    setBusy(true);
    setError(null);
    try {
      // Drop rows missing provider/model — empty pairs aren't valid.
      const clean = rows.filter(
        (r) => r.provider_code.trim() && r.model.trim(),
      );
      const fresh = await putPricing(clean);
      setRows(fresh);
      setSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.somethingWentWrong"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            {t("pricing.title")}
          </h2>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("pricing.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={addRow}
          className="shrink-0 rounded-md border border-neutral-300 px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("pricing.addRow")}
        </button>
      </div>

      {!rows && !error && (
        <p className="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      )}

      {error && (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </p>
      )}

      {rows && rows.length === 0 && !error && (
        <p className="mt-4 text-sm text-neutral-500 dark:text-neutral-400">
          {t("pricing.empty")}
        </p>
      )}

      {rows && rows.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-xs">
            <thead className="bg-neutral-50 dark:bg-neutral-800">
              <tr className="text-left">
                <th className="px-2 py-1">{t("pricing.colProvider")}</th>
                <th className="px-2 py-1">{t("pricing.colModel")}</th>
                <th className="px-2 py-1 text-right">
                  {t("pricing.colInput")}
                </th>
                <th className="px-2 py-1 text-right">
                  {t("pricing.colOutput")}
                </th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-neutral-200 dark:border-neutral-800">
                  <td className="px-2 py-1">
                    <input
                      type="text"
                      value={r.provider_code}
                      onChange={(e) => setRow(i, { provider_code: e.target.value })}
                      placeholder="ai_studio"
                      className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="text"
                      value={r.model}
                      onChange={(e) => setRow(i, { model: e.target.value })}
                      placeholder="gemini-2.5-flash"
                      className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="text"
                      value={r.input_per_1m ?? ""}
                      onChange={(e) =>
                        setRow(i, { input_per_1m: e.target.value || null })
                      }
                      placeholder="0.075"
                      className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-right text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="text"
                      value={r.output_per_1m ?? ""}
                      onChange={(e) =>
                        setRow(i, { output_per_1m: e.target.value || null })
                      }
                      placeholder="0.30"
                      className="w-full rounded-md border border-neutral-300 bg-white px-2 py-1 text-right text-xs dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      title={t("common.delete")}
                      className="text-xs text-neutral-500 hover:text-red-600 dark:text-neutral-400 dark:hover:text-red-400"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={busy || !rows}
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          {busy ? t("common.saving") : t("common.save")}
        </button>
        {savedAt && !busy && (
          <span className="text-xs text-green-700 dark:text-green-400">
            {t("common.saved")}
          </span>
        )}
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          {t("pricing.unitHint")}
        </span>
      </div>
    </section>
  );
}
