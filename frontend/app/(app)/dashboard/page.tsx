"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { articlesForRole } from "@/lib/docs";
import { useT } from "@/lib/i18n-context";

export default function DashboardPage() {
  const { user } = useAuth();
  const { t, lang } = useT();
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "down">(
    "checking",
  );

  useEffect(() => {
    api<{ status: string }>("/health", { noAuth: true })
      .then((r) => setApiStatus(r.status === "ok" ? "ok" : "down"))
      .catch(() => setApiStatus("down"));
  }, []);

  const isRu = lang === "ru";
  const quickArticles = user ? articlesForRole(user.role.name).slice(0, 4) : [];

  return (
    <main className="mx-auto max-w-3xl p-10">
      <h1 className="text-2xl font-semibold">
        {t("dashboard.welcome", { name: user?.full_name ?? user?.email ?? "" })}
      </h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {t("dashboard.role")}: <span className="font-mono">{user?.role.name}</span>
      </p>

      {/* Documentation — pinned at the top so new users notice it. */}
      <section className="mt-8 rounded-lg border border-blue-200 bg-blue-50 p-5 dark:border-blue-900 dark:bg-blue-950/40">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-base font-semibold text-blue-900 dark:text-blue-100">
              <span aria-hidden>📘</span>
              {t("dashboard.docsTitle")}
            </h2>
            <p className="mt-1 text-sm text-blue-900/80 dark:text-blue-100/80">
              {t("dashboard.docsSubtitle")}
            </p>
          </div>
          <Link
            href="/docs"
            className="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-400"
          >
            {t("dashboard.docsCta")}
          </Link>
        </div>

        {quickArticles.length > 0 && (
          <div className="mt-4 border-t border-blue-200 pt-3 dark:border-blue-900">
            <p className="text-xs font-medium uppercase tracking-wide text-blue-900/60 dark:text-blue-100/60">
              {t("dashboard.docsQuickLinks")}
            </p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {quickArticles.map((a) => (
                <li key={a.slug}>
                  <Link
                    href={`/docs/${a.slug}`}
                    className="inline-block rounded-full border border-blue-300 bg-white px-3 py-1 text-xs font-medium text-blue-800 hover:bg-blue-100 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-100 dark:hover:bg-blue-900"
                  >
                    {isRu ? a.titleRu : a.titleEn}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="mt-6 rounded-lg border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-5">
        <h2 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
          {t("dashboard.apiStatus")}
        </h2>
        <p className="mt-1 text-sm">
          {apiStatus === "checking" && (
            <span className="text-neutral-500 dark:text-neutral-400">{t("dashboard.checking")}</span>
          )}
          {apiStatus === "ok" && <span className="text-green-600 dark:text-green-400">{t("dashboard.reachable")}</span>}
          {apiStatus === "down" && <span className="text-red-600 dark:text-red-400">{t("dashboard.unreachable")}</span>}
        </p>
      </section>

      <section className="mt-6 rounded-lg border border-dashed border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 p-5 text-sm text-neutral-500 dark:text-neutral-400">
        {t("dashboard.note")}
      </section>
    </main>
  );
}
