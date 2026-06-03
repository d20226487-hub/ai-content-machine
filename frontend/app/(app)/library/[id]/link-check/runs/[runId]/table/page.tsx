"use client";

import { use, useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import {
  getTranslationTable,
  type TranslationTableRow,
} from "@/lib/linkCheck";

const PAGE_SIZE = 25;

export default function TranslationTablePage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  const [rows, setRows] = useState<TranslationTableRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const r = await getTranslationTable(rid, p, PAGE_SIZE);
        setRows(r.items);
        setTotal(r.total_rows);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [rid],
  );

  useEffect(() => {
    if (Number.isFinite(rid)) void load(page);
  }, [rid, page, load]);

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          {
            label: t("linkCheck.title"),
            href: `/library/${tableId}/link-check`,
          },
          {
            label: t("breadcrumb.run", { id: rid }),
            href: `/library/${tableId}/link-check/runs/${rid}`,
          },
          { label: t("linkCheckRun.rawTableTitle") },
        ]}
      />

      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("linkCheckRun.rawTableTitle")}
      </h1>
      <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
        {t("linkCheckRun.rawTableSubtitle")}
      </p>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </p>
      )}

      {!error && (
        <>
          <div className="mt-4 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50 uppercase tracking-wide text-neutral-500 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-3 py-2 font-medium">
                    {t("linkCheckRun.colRow")}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {t("linkCheckRun.rawOriginal")}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {t("linkCheckRun.rawExpected")}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {t("linkCheckRun.rawTranslation")}
                  </th>
                  <th className="px-3 py-2 font-medium">
                    {t("linkCheckRun.rawMismatches")}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
                {rows.map((r) => (
                  <tr key={r.row_id} className="align-top">
                    <td className="px-3 py-2 tabular-nums text-neutral-500">
                      #{r.row_position + 1}
                    </td>
                    <td className="px-3 py-2">
                      <LinkList links={r.original} />
                    </td>
                    <td className="px-3 py-2">
                      <LinkList links={r.expected} accent="emerald" />
                    </td>
                    <td className="px-3 py-2">
                      <LinkList links={r.translation} />
                    </td>
                    <td className="px-3 py-2">
                      <LinkList links={r.mismatches} accent="red" />
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-3 py-4 text-center text-sm text-neutral-500 dark:text-neutral-400"
                    >
                      {t("linkCheckRun.rawTableEmpty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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

function LinkList({
  links,
  accent,
}: {
  links: string[];
  accent?: "emerald" | "red";
}) {
  if (links.length === 0)
    return <span className="text-neutral-300 dark:text-neutral-600">—</span>;
  const cls =
    accent === "emerald"
      ? "text-emerald-700 hover:underline dark:text-emerald-400"
      : accent === "red"
        ? "text-red-700 hover:underline dark:text-red-400"
        : "text-blue-600 hover:underline dark:text-blue-400";
  return (
    <ul className="space-y-0.5">
      {links.map((l, i) => (
        <li key={`${l}:${i}`}>
          <a
            href={l}
            target="_blank"
            rel="noopener noreferrer"
            className={"break-all " + cls}
          >
            {l}
          </a>
        </li>
      ))}
    </ul>
  );
}
