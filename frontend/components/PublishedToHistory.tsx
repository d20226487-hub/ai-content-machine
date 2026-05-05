"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { useT } from "@/lib/i18n-context";
import { listPublishJobs, type PublishJob } from "@/lib/publish";

const STATUS_BADGE: Record<string, string> = {
  posted: "bg-green-50 text-green-700 ring-green-600/10 dark:bg-green-950/40 dark:text-green-400 dark:ring-green-400/30",
  failed: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-950/40 dark:text-red-400 dark:ring-red-400/30",
  posting: "bg-blue-50 text-blue-700 ring-blue-600/10 dark:bg-blue-950/40 dark:text-blue-400 dark:ring-blue-400/30",
  queued: "bg-neutral-100 text-neutral-700 ring-neutral-600/10 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-500/30",
};

export function PublishedToHistory({ generationId }: { generationId: number }) {
  const { t } = useT();
  const [jobs, setJobs] = useState<PublishJob[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPublishJobs({ generation_id: generationId, page_size: 50 } as never)
      .then((r) => setJobs(r.items))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : t("pubHist.failedLoad")),
      );
  }, [generationId, t]);

  if (error) {
    return (
      <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
        {error}
      </div>
    );
  }

  if (jobs === null) {
    return (
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {t("pubHist.loading")}
      </p>
    );
  }

  if (jobs.length === 0) {
    return (
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {t("pubHist.empty")}
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {t("pubHist.heading")}
      </p>
      <ul className="space-y-1">
        {jobs.map((j) => (
          <li
            key={j.id}
            className="flex flex-wrap items-center gap-2 rounded-md border border-neutral-200 bg-white px-2 py-1 text-xs dark:border-neutral-800 dark:bg-neutral-900"
          >
            <span
              className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset ${STATUS_BADGE[j.status] ?? STATUS_BADGE.queued}`}
            >
              {j.status}
            </span>
            <span className="text-neutral-800 dark:text-neutral-200">
              {j.domain_name ?? t("pubHist.deletedDomain")}
            </span>
            {j.profile_name && (
              <span className="text-neutral-500 dark:text-neutral-400">
                ({j.profile_name})
              </span>
            )}
            {j.language && (
              <span className="text-neutral-500 dark:text-neutral-400">
                · {j.language}
              </span>
            )}
            {j.cms_post_url && (
              <a
                href={j.cms_post_url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto underline text-neutral-700 dark:text-neutral-300"
              >
                {t("pubHist.viewArrow")}
              </a>
            )}
            {!j.cms_post_url && j.error && (
              <span className="ml-auto truncate text-red-700 dark:text-red-400" title={j.error}>
                {j.error}
              </span>
            )}
            <span className="text-neutral-500 dark:text-neutral-400">
              · {new Date(j.created_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
