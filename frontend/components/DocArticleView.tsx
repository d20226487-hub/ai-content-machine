"use client";

import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useAuth } from "@/lib/auth-context";
import type { DocArticle } from "@/lib/docs";
import { useT } from "@/lib/i18n-context";

interface Props {
  article: DocArticle;
  contentRu: string | null;
  contentEn: string | null;
}

export function DocArticleView({ article, contentRu, contentEn }: Props) {
  const { user } = useAuth();
  const { lang } = useT();

  if (!user) return null;
  const isRu = lang === "ru";

  // Role gate.
  if (!article.roles.includes(user.role.name)) {
    return (
      <main className="mx-auto max-w-3xl p-10">
        <Link
          href="/docs"
          className="text-xs text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
        >
          {isRu ? "← К списку статей" : "← Back to articles"}
        </Link>
        <div className="mt-6 rounded-lg border border-neutral-200 bg-white p-5 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
          {isRu
            ? "Эта статья недоступна для вашей роли."
            : "This article is not available for your role."}
        </div>
      </main>
    );
  }

  // Pick content. Prefer requested language; fall back to RU (currently the only fully-written set).
  const requested = isRu ? contentRu : contentEn;
  const content = requested ?? contentRu ?? contentEn;
  const fellBackToRu = !isRu && !contentEn && contentRu !== null;

  return (
    <main className="mx-auto max-w-3xl p-10">
      <Link
        href="/docs"
        className="text-xs text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
      >
        {isRu ? "← К списку статей" : "← Back to articles"}
      </Link>

      {fellBackToRu && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
          The English version of this article is not available yet — showing the
          Russian version.
        </div>
      )}

      {content ? (
        <article className="prose prose-neutral mt-4 max-w-none dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </article>
      ) : (
        <div className="mt-6 rounded-lg border border-neutral-200 bg-white p-5 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
          {isRu ? "Содержимое недоступно." : "Content unavailable."}
        </div>
      )}
    </main>
  );
}
