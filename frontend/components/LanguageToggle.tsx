"use client";

import { useT, type Lang } from "@/lib/i18n-context";

const OPTIONS: { value: Lang; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "ru", label: "RU" },
];

export function LanguageToggle() {
  const { lang, setLang, t } = useT();

  return (
    <div
      role="radiogroup"
      aria-label={t("lang.label")}
      className="flex items-center rounded-md border border-neutral-200 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-900"
    >
      {OPTIONS.map((opt) => {
        const active = lang === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={opt.label}
            onClick={() => setLang(opt.value)}
            className={
              "rounded px-2 py-1 text-[11px] font-semibold transition-colors " +
              (active
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
