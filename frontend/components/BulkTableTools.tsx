"use client";

import Link from "next/link";

import { useT } from "@/lib/i18n-context";

/**
 * Content tools that operate on a whole bulk table, surfaced UNDER the grid
 * (not in the toolbar — the toolbar already holds Generate / Publish and
 * won't fit the growing tool set). Each tool is a card linking to its own
 * page. Find & Replace is the first; the corrector tools land here next.
 */
export function BulkTableTools({ tableId }: { tableId: number }) {
  const { t } = useT();
  return (
    <section className="mt-8">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("tools.heading")}
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <ToolCard
          href={`/library/${tableId}/find-replace`}
          icon="⇄"
          title={t("tools.findReplace.title")}
          description={t("tools.findReplace.desc")}
        />
        <ToolCard
          href={`/library/${tableId}/link-check`}
          icon="🔗"
          title={t("tools.linkCheck.title")}
          description={t("tools.linkCheck.desc")}
        />
        <ToolCard
          href={`/library/${tableId}/structure-format`}
          icon="⊞"
          title={t("tools.structureFormat.title")}
          description={t("tools.structureFormat.desc")}
        />
        <ToolCard
          href={`/library/${tableId}/normalize`}
          icon="⌁"
          title={t("tools.normalize.title")}
          description={t("tools.normalize.desc")}
        />
        <ToolCard
          href={`/library/${tableId}/ai-helper`}
          icon="✨"
          title={t("tools.aiHelper.title")}
          description={t("tools.aiHelper.desc")}
        />
      </div>
    </section>
  );
}

function ToolCard({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group flex items-start gap-3 rounded-lg border border-neutral-200 bg-white p-4 transition hover:border-neutral-300 hover:shadow-sm dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-neutral-100 text-base text-neutral-600 group-hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:group-hover:bg-neutral-700">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-neutral-900 dark:text-neutral-100">
          {title}
        </span>
        <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
          {description}
        </span>
      </span>
    </Link>
  );
}
