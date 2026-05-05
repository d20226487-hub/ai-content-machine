"use client";

import { SingleGenerator } from "@/components/SingleGenerator";
import { useT } from "@/lib/i18n-context";

export default function CreatePage() {
  const { t } = useT();
  return (
    <main className="mx-auto max-w-6xl p-8">
      <div>
        <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
          {t("create.title")}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("create.subtitle")}
        </p>
      </div>

      <div className="mt-8">
        <SingleGenerator />
      </div>
    </main>
  );
}
