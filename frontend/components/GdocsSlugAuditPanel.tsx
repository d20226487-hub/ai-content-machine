"use client";

import { useState } from "react";

import { useT } from "@/lib/i18n-context";
import type { GdocsSlugAudit } from "@/lib/types";

/**
 * "AI slug mapping" audit panel for Google-Docs-imported tables.
 *
 * Shows, per row, what the AI pairing did to the slug: the raw link anchor the
 * writer attached ("before") → the final slug taken from Structure ("after"),
 * with the SEO title + language for context. Rows the AI changed are tinted
 * amber; rows it couldn't pair (no-exact-slug) are tinted red — so the operator
 * can quickly check + track the import. Reflects the import-time decision (not
 * later manual slug edits). Collapsed by default.
 */
export function GdocsSlugAuditPanel({
  rows,
  multiSite,
}: {
  rows: GdocsSlugAudit[];
  multiSite: boolean;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  if (!rows || rows.length === 0) return null;

  const changed = rows.filter((r) => r.changed && !r.unmatched).length;
  const unmatched = rows.filter((r) => r.unmatched).length;

  return (
    <section className="mt-6 rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
          {t("gdocsSlugAudit.heading")}
        </span>
        <span className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          {t("gdocsSlugAudit.summary", {
            total: rows.length,
            changed,
            unmatched,
          })}
          <span aria-hidden>{open ? "▴" : "▾"}</span>
        </span>
      </button>

      {open && (
        <div className="border-t border-neutral-200 px-4 py-4 dark:border-neutral-800">
          <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
            {t("gdocsSlugAudit.help")}
          </p>
          <div className="max-h-[28rem] overflow-auto rounded-md border border-neutral-200 dark:border-neutral-800">
            <table className="w-full border-collapse text-xs">
              <thead className="sticky top-0 bg-neutral-50 text-left text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400">
                <tr>
                  <th className="px-2 py-1.5 font-medium">#</th>
                  {multiSite && (
                    <th className="px-2 py-1.5 font-medium">
                      {t("gdocsSlugAudit.colDomain")}
                    </th>
                  )}
                  <th className="px-2 py-1.5 font-medium">
                    {t("gdocsSlugAudit.colLang")}
                  </th>
                  <th className="px-2 py-1.5 font-medium">
                    {t("gdocsSlugAudit.colSeoTitle")}
                  </th>
                  <th className="px-2 py-1.5 font-medium">
                    {t("gdocsSlugAudit.colBefore")}
                  </th>
                  <th className="px-2 py-1.5 font-medium">
                    {t("gdocsSlugAudit.colAfter")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const tint = r.unmatched
                    ? "bg-red-50/60 dark:bg-red-950/20"
                    : r.changed
                      ? "bg-amber-50/60 dark:bg-amber-950/20"
                      : "";
                  return (
                    <tr
                      key={r.row}
                      className={
                        "border-t border-neutral-100 align-top dark:border-neutral-800/70 " +
                        tint
                      }
                    >
                      <td className="px-2 py-1.5 tabular-nums text-neutral-500 dark:text-neutral-400">
                        {r.row}
                      </td>
                      {multiSite && (
                        <td className="max-w-[12rem] truncate px-2 py-1.5 text-neutral-600 dark:text-neutral-400" title={r.domain}>
                          {r.domain}
                        </td>
                      )}
                      <td className="px-2 py-1.5 uppercase text-neutral-500 dark:text-neutral-400">
                        {r.language}
                      </td>
                      <td className="max-w-[20rem] truncate px-2 py-1.5 text-neutral-800 dark:text-neutral-200" title={r.seo_title}>
                        {r.seo_title}
                      </td>
                      <td className="max-w-[16rem] truncate px-2 py-1.5 font-mono text-neutral-500 dark:text-neutral-400" title={r.anchor}>
                        {r.anchor || "—"}
                      </td>
                      <td
                        className={
                          "max-w-[16rem] truncate px-2 py-1.5 font-mono " +
                          (r.unmatched
                            ? "text-red-700 dark:text-red-400"
                            : "text-neutral-900 dark:text-neutral-100")
                        }
                        title={r.slug}
                      >
                        {r.slug}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
