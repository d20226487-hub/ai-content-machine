"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BackupCard } from "@/components/BackupCard";
import { BrainCard } from "@/components/BrainCard";
import { GenerationDefaultsCard } from "@/components/GenerationDefaultsCard";
import { PricingCard } from "@/components/PricingCard";
import { TrashRetentionCard } from "@/components/TrashRetentionCard";
import { ProviderCard } from "@/components/ProviderCard";
import { PublishDefaultsCard } from "@/components/PublishDefaultsCard";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT, type TranslationKey } from "@/lib/i18n-context";
import { listProviders } from "@/lib/settings";
import type { Provider } from "@/lib/types";

type TabKey =
  | "providers"
  | "generation"
  | "publishing"
  | "pricing"
  | "backups"
  | "trash"
  | "brain";

const TABS: { key: TabKey; labelKey: TranslationKey }[] = [
  { key: "providers", labelKey: "settings.tab.providers" },
  { key: "generation", labelKey: "settings.tab.generation" },
  { key: "publishing", labelKey: "settings.tab.publishing" },
  { key: "pricing", labelKey: "settings.tab.pricing" },
  { key: "backups", labelKey: "settings.tab.backups" },
  { key: "trash", labelKey: "settings.tab.trash" },
  { key: "brain", labelKey: "settings.tab.brain" },
];

function isTabKey(v: string | null): v is TabKey {
  return !!v && TABS.some((t) => t.key === v);
}

export default function SettingsPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const initialTab = useMemo<TabKey>(() => {
    const v = sp.get("tab");
    return isTabKey(v) ? v : "providers";
  }, [sp]);
  const [tab, setTab] = useState<TabKey>(initialTab);

  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && user && user.role.name !== "admin") {
      router.replace("/dashboard");
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!user || user.role.name !== "admin") return;
    if (tab !== "providers") return;
    if (providers !== null) return;
    listProviders()
      .then(setProviders)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [user, t, tab, providers]);

  if (authLoading || !user) return null;

  function selectTab(next: TabKey) {
    setTab(next);
    const params = new URLSearchParams(sp.toString());
    if (next === "providers") params.delete("tab");
    else params.set("tab", next);
    const qs = params.toString();
    router.replace(`/settings${qs ? "?" + qs : ""}`);
  }

  function replaceProvider(updated: Provider) {
    setProviders((list) =>
      list ? list.map((p) => (p.code === updated.code ? updated : p)) : list,
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-10">
      <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        {t("settings.title")}
      </h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {t("settings.subtitle")}
      </p>

      <div className="mt-8 border-b border-neutral-200 dark:border-neutral-800">
        <nav
          className="-mb-px flex flex-wrap gap-x-6 gap-y-1"
          aria-label={t("settings.tabsAria")}
        >
          {TABS.map((tabDef) => {
            const active = tab === tabDef.key;
            return (
              <button
                key={tabDef.key}
                type="button"
                onClick={() => selectTab(tabDef.key)}
                className={
                  "whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors " +
                  (active
                    ? "border-neutral-900 text-neutral-900 dark:border-neutral-100 dark:text-neutral-100"
                    : "border-transparent text-neutral-500 hover:border-neutral-300 hover:text-neutral-700 dark:text-neutral-400 dark:hover:border-neutral-700 dark:hover:text-neutral-200")
                }
                aria-current={active ? "page" : undefined}
                data-tab={tabDef.key}
              >
                {t(tabDef.labelKey)}
              </button>
            );
          })}
        </nav>
      </div>

      {loadError && tab === "providers" && (
        <p className="mt-6 rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {loadError}
        </p>
      )}

      <div className="mt-8">
        {tab === "providers" && (
          <>
            {!providers && !loadError && (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {t("settings.loadingProviders")}
              </p>
            )}
            {providers && (
              <div className="flex flex-col gap-6">
                {providers.map((p) => (
                  <ProviderCard
                    key={p.code}
                    provider={p}
                    onUpdated={replaceProvider}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {tab === "generation" && <GenerationDefaultsCard />}
        {tab === "publishing" && <PublishDefaultsCard />}
        {tab === "pricing" && <PricingCard />}
        {tab === "backups" && <BackupCard />}
        {tab === "trash" && <TrashRetentionCard />}
        {tab === "brain" && <BrainCard />}
      </div>
    </main>
  );
}
