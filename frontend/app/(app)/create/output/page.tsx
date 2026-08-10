"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { SingleOutputView } from "@/components/SingleOutputView";
import { type CreateSession, readSession } from "@/lib/createSession";
import { useT } from "@/lib/i18n-context";
import { clearPendingNav } from "@/lib/pendingNav";

/**
 * Dedicated view for the most recent /create generation. Lets the
 * output get the full viewport while the form is tucked one click
 * away. Reads its state from sessionStorage (written by
 * SingleGenerator on Generate / loadSaved). A direct visit with no
 * stored result bounces back to /create.
 */
export default function CreateOutputPage() {
  const router = useRouter();
  const { t } = useT();

  // Stored as state (not a ref) so a savedId change from the child
  // re-renders the page title meta cleanly. The initial value is
  // hydrated client-side only — server-rendered Next.js page would
  // have no access to sessionStorage on the first paint.
  const [session, setSession] = useState<CreateSession | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // Arrived — drop the recovery marker so it can't affect a later failure.
    clearPendingNav();
    const s = readSession();
    setSession(s);
    setHydrated(true);
    if (!s || !s.result) {
      // Bounce: nothing to display. router.replace so the back stack
      // points at wherever the user came from before /create rather
      // than this empty output page.
      router.replace("/create");
    }
  }, [router]);

  const title = useMemo(() => {
    if (!session) return t("create.title");
    if (session.viewingSaved) return session.viewingSaved.name;
    return session.form.selectedPromptName ?? t("create.title");
  }, [session, t]);

  if (!hydrated || !session || !session.result) {
    return (
      <main className="mx-auto max-w-6xl p-8">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {t("common.loading")}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-6">
        <h1 className="truncate text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
          {title}
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          {t("single.outputSubtitle")}
        </p>
      </header>

      <SingleOutputView
        session={session}
        onSavedIdChange={(savedId) =>
          setSession((cur) => (cur ? { ...cur, savedId } : cur))
        }
      />
    </main>
  );
}
