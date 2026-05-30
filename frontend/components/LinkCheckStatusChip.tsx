"use client";

import { useT } from "@/lib/i18n-context";
import type { LinkCheckStatus } from "@/lib/linkCheck";

export function LinkCheckStatusChip({ status }: { status: LinkCheckStatus }) {
  const { t } = useT();
  const cls =
    status === "running" || status === "queued"
      ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
      : status === "done"
        ? "bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300"
        : status === "cancelled"
          ? "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400"
          : "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300";
  const label =
    status === "queued"
      ? t("linkCheck.statusQueued")
      : status === "running"
        ? t("linkCheck.statusRunning")
        : status === "done"
          ? t("linkCheck.statusDone")
          : status === "cancelled"
            ? t("linkCheck.statusCancelled")
            : t("linkCheck.statusFailed");
  return <span className={"rounded-full px-2 py-0.5 " + cls}>{label}</span>;
}
