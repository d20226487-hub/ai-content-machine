"use client";

import { useState } from "react";

import { useT } from "@/lib/i18n-context";
import type { GdocsSiteStructure } from "@/lib/types";

/**
 * "Site structure" reference panel for Google-Docs-imported tables.
 *
 * Shows each site's full planned page list (from the sheet's Structure column)
 * — including pages that don't yet have a written Doc, which therefore aren't
 * rows in the table. It's reference material: the operator can see the intended
 * site map and copy it to supply to an AI (e.g. to draft the missing pages).
 * Collapsed by default so it doesn't crowd the grid.
 */
export function GdocsStructurePanel({
  sites,
}: {
  sites: GdocsSiteStructure[];
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  if (!sites || sites.length === 0) return null;

  const totalPages = sites.reduce((n, s) => n + s.structure.length, 0);

  return (
    <section className="mt-6 rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
          {t("gdocsStructure.heading")}
        </span>
        <span className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          {t("gdocsStructure.summary", {
            sites: sites.length,
            pages: totalPages,
          })}
          <span aria-hidden>{open ? "▴" : "▾"}</span>
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-neutral-200 px-4 py-4 dark:border-neutral-800">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {t("gdocsStructure.help")}
          </p>
          {sites.map((site, i) => (
            <SiteBlock key={`${site.domain}-${i}`} site={site} />
          ))}
        </div>
      )}
    </section>
  );
}

function SiteBlock({ site }: { site: GdocsSiteStructure }) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(site.structure.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can fail (permissions / insecure context) — ignore quietly.
    }
  }

  return (
    <div className="rounded-md border border-neutral-200 dark:border-neutral-800">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-200 bg-neutral-50 px-3 py-2 dark:border-neutral-800 dark:bg-neutral-900/40">
        <p className="min-w-0 truncate text-sm font-medium text-neutral-800 dark:text-neutral-200">
          {site.domain || t("gdocsStructure.noDomain")}
          {site.language && (
            <span className="ml-2 rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
              {site.language}
            </span>
          )}
        </p>
        <button
          type="button"
          onClick={copy}
          className="shrink-0 rounded border border-neutral-300 px-2 py-0.5 text-xs font-medium text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
        >
          {copied ? t("gdocsStructure.copied") : t("gdocsStructure.copy")}
        </button>
      </div>
      <ol className="max-h-72 space-y-0.5 overflow-auto px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
        {site.structure.map((line, i) => (
          <li key={i} className="border-l-2 border-neutral-200 pl-2 dark:border-neutral-700">
            {line}
          </li>
        ))}
      </ol>
    </div>
  );
}
