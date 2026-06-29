"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useT, type TranslationKey } from "@/lib/i18n-context";

const TABS: { href: string; labelKey: TranslationKey }[] = [
  { href: "/publish/domains", labelKey: "publish.tabDomains" },
  { href: "/publish/languages", labelKey: "publish.tabLanguages" },
  { href: "/publish/autotool", labelKey: "publish.tabAutotool" },
  { href: "/publish/post", labelKey: "publish.tabSingleRuns" },
  { href: "/publish/runs", labelKey: "publish.tabBulkRuns" },
  { href: "/publish/cache/runs", labelKey: "publish.tabCacheRuns" },
];

export default function PublishLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useT();
  return (
    <div>
      <nav className="border-b border-neutral-200 bg-white px-5 dark:border-neutral-800 dark:bg-neutral-900">
        <ul className="-mb-px flex gap-1">
          {TABS.map((tab) => {
            const active = pathname === tab.href || pathname.startsWith(tab.href + "/");
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  className={
                    "inline-block border-b-2 px-3 py-2 text-sm font-medium transition-colors " +
                    (active
                      ? "border-neutral-900 text-neutral-900 dark:border-neutral-100 dark:text-neutral-100"
                      : "border-transparent text-neutral-500 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100")
                  }
                >
                  {t(tab.labelKey)}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {children}
    </div>
  );
}
