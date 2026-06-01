"use client";

import Link from "next/link";

import { useT } from "@/lib/i18n-context";

export interface Crumb {
  label: string;
  /** Omit on the current (last) crumb. */
  href?: string;
}

/**
 * Breadcrumb trail for a bulk-table tool page, in logical order:
 * ``Back to table › Tool › Run``. The first segment links back to the
 * bulk table; callers pass only the trailing segments.
 *
 * Pass ``tableId={0}`` (or non-finite) to skip the table segment when the
 * id isn't known yet — the trail still renders.
 */
export function ToolBreadcrumb({
  tableId,
  trail,
}: {
  tableId: number;
  trail: Crumb[];
}) {
  const { t } = useT();

  const segments: Crumb[] =
    Number.isFinite(tableId) && tableId > 0
      ? [
          { label: t("breadcrumb.table"), href: `/library/${tableId}` },
          ...trail,
        ]
      : trail;

  return (
    <nav className="mb-4 flex flex-wrap items-center gap-1.5 text-sm text-neutral-600 dark:text-neutral-400">
      {segments.map((s, i) => {
        const isLast = i === segments.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="text-neutral-400 dark:text-neutral-600">›</span>
            )}
            {isLast || !s.href ? (
              <span
                className={
                  isLast
                    ? "font-medium text-neutral-900 dark:text-neutral-100"
                    : undefined
                }
              >
                {s.label}
              </span>
            ) : (
              <Link
                href={s.href}
                className="hover:text-neutral-900 hover:underline dark:hover:text-neutral-100"
              >
                {s.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
