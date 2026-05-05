"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth-context";
import { articlesForRole } from "@/lib/docs";
import { useT } from "@/lib/i18n-context";

export default function DocsIndexPage() {
  const { user } = useAuth();
  const { lang } = useT();

  if (!user) return null;

  const articles = articlesForRole(user.role.name);
  const isRu = lang === "ru";

  return (
    <main className="mx-auto max-w-4xl p-10">
      <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        {isRu ? "Документация" : "Documentation"}
      </h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {isRu
          ? "Руководства по разделам системы. Видны только статьи, доступные для вашей роли."
          : "Section-by-section guides. Only articles available to your role are shown."}
      </p>

      <ul className="mt-6 grid gap-3 sm:grid-cols-2">
        {articles.map((a) => (
          <li key={a.slug}>
            <Link
              href={`/docs/${a.slug}`}
              className="block rounded-lg border border-neutral-200 bg-white p-4 transition-colors hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700 dark:hover:bg-neutral-850"
            >
              <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                {isRu ? a.titleRu : a.titleEn}
              </h2>
              <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                {isRu ? a.summaryRu : a.summaryEn}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
