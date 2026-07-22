"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { HtmlViewer } from "@/components/HtmlViewer";
import { LanguageToggle } from "@/components/LanguageToggle";
import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getSharedCell, type SharedCell } from "@/lib/share";

/**
 * Public, read-only view of ONE shared cell — for someone with no ACM account.
 *
 * Deliberately standalone: no app chrome, no navigation into the workspace, and
 * nothing here assumes a logged-in user. The content itself is rendered by
 * HtmlViewer, which hosts it in a fully sandboxed iframe, so AI-generated HTML
 * can't execute against our origin. Mobile-first — most of these links get
 * opened on a phone.
 */
export default function SharedPreviewPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  const { t } = useT();

  const [cell, setCell] = useState<SharedCell | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getSharedCell(token)
      .then((c) => {
        if (!cancelled) setCell(c);
      })
      .catch((e) => {
        if (cancelled) return;
        // The API returns one generic 404 for unknown / revoked / expired.
        setError(
          e instanceof ApiError && e.status === 404
            ? t("share.notFound")
            : t("share.loadFailed"),
        );
      });
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  return (
    <main className="min-h-screen bg-neutral-50 dark:bg-neutral-950">
      <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6 sm:py-10">
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-neutral-400 dark:text-neutral-500">
              {t("share.pageEyebrow")}
            </p>
            {cell && (
              <h1 className="mt-0.5 break-words text-lg font-semibold text-neutral-900 dark:text-neutral-100 sm:text-xl">
                {cell.column_name}
                <span className="ml-2 text-sm font-normal text-neutral-500 dark:text-neutral-400">
                  {t("share.rowNumber", { n: cell.row_number })}
                </span>
              </h1>
            )}
          </div>
          <LanguageToggle />
        </header>

        {error && (
          <div className="rounded-lg border border-neutral-200 bg-white px-4 py-10 text-center dark:border-neutral-800 dark:bg-neutral-900">
            <p className="text-sm text-neutral-700 dark:text-neutral-300">
              {error}
            </p>
          </div>
        )}

        {!cell && !error && (
          <p className="px-1 py-10 text-center text-sm text-neutral-500 dark:text-neutral-400">
            {t("common.loading")}
          </p>
        )}

        {cell && (
          <>
            {/* 70vh keeps the reading pane proportional on a phone and on a
                desktop without a fixed pixel height fighting either. */}
            <HtmlViewer content={cell.content} title="" height="h-[70vh]" />
            <p className="mt-4 text-center text-xs text-neutral-500 dark:text-neutral-400">
              {t("share.footerNote", {
                date: new Date(cell.expires_at).toLocaleDateString(),
              })}
            </p>
          </>
        )}
      </div>
    </main>
  );
}
