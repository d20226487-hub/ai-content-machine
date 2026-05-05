"use client";

import { useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";

interface Props {
  /** One-line summary shown at the top. */
  title?: string;
  /** Either an Error/ApiError or a raw string. */
  error: unknown;
  /** Hide the expandable details if you only want the headline. */
  showDetails?: boolean;
}

/**
 * Reusable error display. Shows a headline and an expandable section with the
 * full message + status code + stack (if any) + a Copy button.
 */
export function ErrorPanel({ title, error, showDetails = true }: Props) {
  const { t } = useT();
  const headingTitle = title ?? t("common.somethingWentWrong");
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const { headline, status, fullText } = toParts(error);

  function copy() {
    void navigator.clipboard.writeText(fullText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm dark:border-red-900/60 dark:bg-red-950/40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-red-800 dark:text-red-200">
            {headingTitle}
            {status != null && (
              <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-mono uppercase text-red-700 dark:bg-red-900/60 dark:text-red-200">
                HTTP {status}
              </span>
            )}
          </p>
          <p className="mt-0.5 break-words text-red-700 dark:text-red-300">{headline}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs">
          <button
            type="button"
            onClick={copy}
            className="rounded border border-red-300 px-2 py-0.5 font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-900/30"
          >
            {copied ? t("common.copied") : t("common.copy")}
          </button>
          {showDetails && headline !== fullText && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="rounded border border-red-300 px-2 py-0.5 font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-900/30"
            >
              {open ? t("common.hide") : t("common.details")}
            </button>
          )}
        </div>
      </div>

      {open && (
        <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded bg-red-100/60 p-2 font-mono text-[11px] leading-relaxed text-red-900 dark:bg-red-950 dark:text-red-200">
          {fullText}
        </pre>
      )}
    </div>
  );
}

interface Parts {
  headline: string;
  status: number | undefined;
  fullText: string;
}

function toParts(error: unknown): Parts {
  if (error instanceof ApiError) {
    const detailObj =
      typeof error.detail === "object" && error.detail !== null ? error.detail : null;
    const fullText = detailObj
      ? `HTTP ${error.status}\n\n${error.message}\n\n--- raw ---\n${safeStringify(detailObj)}`
      : `HTTP ${error.status}\n\n${error.message}`;
    return {
      headline: collapseToSingleLine(error.message),
      status: error.status,
      fullText,
    };
  }
  if (error instanceof Error) {
    return {
      headline: collapseToSingleLine(error.message),
      status: undefined,
      fullText: error.stack ?? error.message,
    };
  }
  const s = typeof error === "string" ? error : safeStringify(error);
  return { headline: collapseToSingleLine(s), status: undefined, fullText: s };
}

function collapseToSingleLine(s: string): string {
  // Take the first non-empty line, trimmed; cap length so the headline stays compact.
  const first = (s.split(/\r?\n/).find((l) => l.trim()) ?? s).trim();
  return first.length > 240 ? first.slice(0, 240) + "…" : first;
}

function safeStringify(x: unknown): string {
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
}
