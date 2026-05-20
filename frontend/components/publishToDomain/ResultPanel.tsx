"use client";

import { useT } from "@/lib/i18n-context";
import type { PublishJobDetail } from "@/lib/publish";

/**
 * Renders the success banner + warnings list + error block for the
 * single-publish modal. Pure read-only display — all state transitions
 * happen in the parent.
 *
 * Three independent slots that can stack:
 *   1. Error block (when the request failed or the worker returned a
 *      non-posted terminal status).
 *   2. Success banner with optional "View post" link (only after a
 *      successful publish).
 *   3. Warnings list (e.g. featured-media upload failed but the rest
 *      of the post landed — captured non-fatally by the worker).
 */
export function ResultPanel({
  error,
  result,
}: {
  error: string | null;
  result: PublishJobDetail | null;
}) {
  const { t } = useT();
  return (
    <>
      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      )}

      {result && result.status === "posted" && (
        <div className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800 dark:bg-green-950/40 dark:text-green-300">
          {t("pubMod.published")}
          {result.cms_post_url && (
            <>
              {" "}
              <a
                href={result.cms_post_url}
                target="_blank"
                rel="noreferrer"
                className="underline"
              >
                {t("pubMod.viewPost")}
              </a>
            </>
          )}
        </div>
      )}

      {result?.warnings && result.warnings.length > 0 && (
        <div className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          <p className="font-medium">{t("pubMod.warnings")}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
