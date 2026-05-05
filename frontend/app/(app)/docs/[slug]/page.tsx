import { promises as fs } from "fs";
import path from "path";
import { notFound } from "next/navigation";

import { DocArticleView } from "@/components/DocArticleView";
import { DOC_ARTICLES, getArticle } from "@/lib/docs";

export function generateStaticParams() {
  return DOC_ARTICLES.map((a) => ({ slug: a.slug }));
}

async function readMarkdown(slug: string, lang: "ru" | "en"): Promise<string | null> {
  const file = path.join(process.cwd(), "content", "docs", lang, `${slug}.md`);
  try {
    return await fs.readFile(file, "utf-8");
  } catch {
    return null;
  }
}

export default async function DocArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) notFound();

  const ru = await readMarkdown(slug, "ru");
  const en = await readMarkdown(slug, "en");

  return <DocArticleView article={article} contentRu={ru} contentEn={en} />;
}
