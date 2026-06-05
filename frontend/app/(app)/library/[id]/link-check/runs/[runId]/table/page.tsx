"use client";

import Link from "next/link";
import { use } from "react";

import { ToolBreadcrumb } from "@/components/ToolBreadcrumb";
import { TranslationTableView } from "@/components/TranslationTableView";
import { useT } from "@/lib/i18n-context";

export default function TranslationTablePage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const tableId = Number(id);
  const rid = Number(runId);
  const { t } = useT();

  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <ToolBreadcrumb
        tableId={tableId}
        trail={[
          { label: t("linkCheck.title"), href: `/library/${tableId}/link-check` },
          {
            label: t("breadcrumb.run", { id: rid }),
            href: `/library/${tableId}/link-check/runs/${rid}`,
          },
          { label: t("linkCheckRun.rawTableTitle") },
        ]}
      />

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
            {t("linkCheckRun.rawTableTitle")}
          </h1>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            {t("linkCheckRun.rawTableSubtitle")}
          </p>
        </div>
        <Link
          href={`/library/${tableId}/link-check?rerun=${rid}`}
          className="shrink-0 rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-800 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {t("linkCheckRun.rerunWithChanges")}
        </Link>
      </div>

      <div className="mt-4">
        <TranslationTableView runId={rid} tableId={tableId} />
      </div>
    </main>
  );
}
