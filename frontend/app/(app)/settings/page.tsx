"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { BackupCard } from "@/components/BackupCard";
import { PricingCard } from "@/components/PricingCard";
import { TrashRetentionCard } from "@/components/TrashRetentionCard";
import { ProviderCard } from "@/components/ProviderCard";
import { PublishDefaultsCard } from "@/components/PublishDefaultsCard";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useT } from "@/lib/i18n-context";
import { listProviders } from "@/lib/settings";
import type { Provider } from "@/lib/types";

export default function SettingsPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { t } = useT();

  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && user && user.role.name !== "admin") {
      router.replace("/dashboard");
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (!user || user.role.name !== "admin") return;
    listProviders()
      .then(setProviders)
      .catch((err) =>
        setLoadError(err instanceof ApiError ? err.message : t("common.failedToLoad")),
      );
  }, [user, t]);

  if (authLoading || !user) return null;

  function replace(updated: Provider) {
    setProviders((list) =>
      list ? list.map((p) => (p.code === updated.code ? updated : p)) : list,
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-10">
      <h1 className="text-2xl font-semibold text-neutral-900 dark:text-neutral-100">{t("settings.title")}</h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        {t("settings.subtitle")}
      </p>

      {loadError && (
        <p className="mt-6 rounded-md bg-red-50 dark:bg-red-950/50 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {loadError}
        </p>
      )}

      {!providers && !loadError && (
        <p className="mt-8 text-sm text-neutral-500 dark:text-neutral-400">{t("settings.loadingProviders")}</p>
      )}

      {providers && (
        <div className="mt-8 flex flex-col gap-6">
          {providers.map((p) => (
            <ProviderCard key={p.code} provider={p} onUpdated={replace} />
          ))}
        </div>
      )}

      <div className="mt-10">
        <PublishDefaultsCard />
      </div>

      <div className="mt-10">
        <PricingCard />
      </div>

      <div className="mt-10">
        <BackupCard />
      </div>

      <div className="mt-10">
        <TrashRetentionCard />
      </div>
    </main>
  );
}
