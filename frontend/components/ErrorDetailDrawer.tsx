"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { getError, type ErrorLogDetail } from "@/lib/errors";

export function ErrorDetailDrawer({
  errorId,
  onClose,
  onDelete,
}: {
  errorId: number;
  onClose: () => void;
  onDelete?: (id: number) => void;
}) {
  const { t } = useT();
  const [detail, setDetail] = useState<ErrorLogDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    getError(errorId)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [errorId, t]);

  function copyJson() {
    if (!detail) return;
    void navigator.clipboard.writeText(JSON.stringify(detail, null, 2));
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex"
      onClick={onClose}
    >
      <div className="flex-1 bg-black/30" />
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-2xl flex-col bg-white shadow-xl dark:bg-neutral-900"
      >
        <header className="flex items-center justify-between border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <div>
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              {t("errors.detailTitle", { id: errorId })}
            </h2>
            {detail && (
              <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                {new Date(detail.created_at).toLocaleString()}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={copyJson}
              disabled={!detail}
              className="rounded-md border border-neutral-300 px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {t("errors.copyJson")}
            </button>
            {onDelete && detail && (
              <button
                onClick={() => onDelete(detail.id)}
                className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:border-red-800/60 dark:text-red-400 dark:hover:bg-red-950/40"
              >
                {t("common.delete")}
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-md p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
              aria-label={t("common.close")}
            >
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                <path
                  d="M5 5l10 10M15 5L5 15"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-auto px-5 py-4">
          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </div>
          )}
          {!detail && !error && (
            <p className="text-sm text-neutral-500">{t("common.loading")}</p>
          )}
          {detail && (
            <div className="space-y-4">
              <Section label={t("errors.sectionMessage")}>
                <p className="whitespace-pre-wrap break-words text-sm text-neutral-900 dark:text-neutral-100">
                  {detail.message}
                </p>
              </Section>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <Field label={t("errors.fieldSource")} value={detail.source} />
                <Field label={t("errors.fieldCategory")} value={detail.category} />
                <Field label={t("errors.fieldProvider")} value={detail.provider ?? "—"} />
                <Field
                  label={t("errors.fieldStatusCode")}
                  value={detail.status_code !== null ? String(detail.status_code) : "—"}
                />
                <Field label={t("errors.fieldUser")} value={detail.user_email ?? "—"} />
                <Field
                  label={t("errors.fieldResource")}
                  value={
                    detail.resource_type
                      ? `${detail.resource_type}#${detail.resource_id ?? ""}`
                      : "—"
                  }
                />
              </div>

              {Object.keys(detail.context_json ?? {}).length > 0 && (
                <Section label={t("errors.sectionContext")}>
                  <pre className="max-h-72 overflow-auto rounded-md bg-neutral-50 p-3 text-xs text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
                    {JSON.stringify(detail.context_json, null, 2)}
                  </pre>
                </Section>
              )}

              {detail.stack_trace && (
                <Section label={t("errors.sectionStack")}>
                  <pre className="max-h-96 overflow-auto rounded-md bg-neutral-50 p-3 text-xs text-neutral-800 dark:bg-neutral-950 dark:text-neutral-200">
                    {detail.stack_trace}
                  </pre>
                </Section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </h3>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {label}
      </dt>
      <dd className="mt-0.5 text-sm text-neutral-900 dark:text-neutral-100">{value}</dd>
    </div>
  );
}
